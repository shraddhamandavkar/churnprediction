"""
ChurnGuard - Enterprise Telecom Customer Churn Prediction & Retention Engine
Production Flask Backend
"""
import io
import os
import sqlite3
from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
import joblib
import pandas as pd
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "churn_guard_secure_key_2026")

DATABASE_NAME = "churnguard.db"
MODEL_PATH = "churn_model.pkl"
COLUMNS_PATH = "model_columns.pkl"


def get_db_connection():
    """Establishes an SQLite connection with WAL mode and a 30s timeout to prevent locking."""
    conn = sqlite3.connect(DATABASE_NAME, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db():
    """Auto-generates the database schema if running on a fresh container or machine."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'agent'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenure INTEGER,
                contract TEXT,
                monthly_charges REAL,
                total_charges REAL,
                internet_service TEXT,
                payment_method TEXT,
                churn TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                prediction TEXT,
                probability REAL,
                risk_level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retention_campaigns (
                campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                offer_type TEXT,
                discount_percent REAL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Sent',
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


# Ensure tables exist on server startup
init_db()


def calculate_churn_risk(data_dict):
    """Aligns incoming features against model training columns and runs inference."""
    try:
        if os.path.exists(MODEL_PATH) and os.path.exists(COLUMNS_PATH):
            model = joblib.load(MODEL_PATH)
            model_cols = joblib.load(COLUMNS_PATH)

            input_df = pd.DataFrame([data_dict])

            # Safely verify and convert TotalCharges without attribute errors
            if "TotalCharges" not in input_df.columns:
                input_df["TotalCharges"] = 0.0
            input_df["TotalCharges"] = pd.to_numeric(input_df["TotalCharges"], errors="coerce").fillna(0.0)

            encoded_df = pd.get_dummies(input_df)
            aligned_df = encoded_df.reindex(columns=model_cols, fill_value=0)

            prob = float(model.predict_proba(aligned_df)[0][1]) * 100
            pred = "Churn" if prob >= 50.0 else "No Churn"
            risk_level = "High Risk" if prob >= 50.0 else "Low Risk"
            return round(prob, 2), risk_level, pred
    except Exception as e:
        print(f"[ML INFERENCE FALLBACK]: {e}")

    # Fallback heuristic calculation if model artifacts are unavailable
    tenure = float(data_dict.get("tenure", 1))
    monthly = float(data_dict.get("MonthlyCharges", 50.0))
    contract = str(data_dict.get("Contract", "Month-to-month"))

    score = 0
    if tenure <= 12:
        score += 40
    if contract == "Month-to-month":
        score += 35
    if monthly > 70:
        score += 20

    prob = min(max(float(score), 5.0), 95.0)
    risk_level = "High Risk" if prob >= 50.0 else "Low Risk"
    pred = "Churn" if prob >= 50.0 else "No Churn"
    return round(prob, 2), risk_level, pred


# ----------------- Auth & Navigation -----------------


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_db_connection()
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        finally:
            conn.close()

        if user:
            stored_pwd = user["password"]
            is_valid = False
            if stored_pwd.startswith("scrypt:") or stored_pwd.startswith("pbkdf2:"):
                is_valid = check_password_hash(stored_pwd, password)
            else:
                is_valid = stored_pwd == password

            if is_valid:
                session["user_id"] = user["user_id"]
                session["user_name"] = user["name"]
                session["role"] = user["role"]
                flash("Login successful!", "success")
                return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_db_connection()
        try:
            existing = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                flash("Email address already exists.", "danger")
                return redirect(url_for("register"))

            hashed_pw = generate_password_hash(password)
            conn.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, 'agent')",
                (name, email, hashed_pw),
            )
            conn.commit()
        finally:
            conn.close()

        flash("Account created successfully! Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ----------------- Prediction Route (Shows Results on Predict Page) -----------------


@app.route("/predict", methods=["GET", "POST"])
def predict():
    if "user_id" not in session:
        return redirect(url_for("login"))

    result = None

    if request.method == "POST":
        form_data = {
            "gender": request.form.get("gender", "Male"),
            "SeniorCitizen": int(request.form.get("SeniorCitizen", 0)),
            "Partner": request.form.get("Partner", "No"),
            "Dependents": request.form.get("Dependents", "No"),
            "tenure": int(request.form.get("tenure", 1)),
            "PhoneService": request.form.get("PhoneService", "Yes"),
            "MultipleLines": request.form.get("MultipleLines", "No"),
            "InternetService": request.form.get("InternetService", "Fiber optic"),
            "OnlineSecurity": request.form.get("OnlineSecurity", "No"),
            "OnlineBackup": request.form.get("OnlineBackup", "No"),
            "DeviceProtection": request.form.get("DeviceProtection", "No"),
            "TechSupport": request.form.get("TechSupport", "No"),
            "StreamingTV": request.form.get("StreamingTV", "No"),
            "StreamingMovies": request.form.get("StreamingMovies", "No"),
            "Contract": request.form.get("Contract", "Month-to-month"),
            "PaperlessBilling": request.form.get("PaperlessBilling", "Yes"),
            "PaymentMethod": request.form.get("PaymentMethod", "Electronic check"),
            "MonthlyCharges": float(request.form.get("MonthlyCharges", 65.0)),
            "TotalCharges": float(request.form.get("TotalCharges", 65.0)),
        }

        prob, risk, pred = calculate_churn_risk(form_data)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO customers 
                (tenure, contract, monthly_charges, total_charges, internet_service, payment_method, churn) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    form_data["tenure"],
                    form_data["Contract"],
                    form_data["MonthlyCharges"],
                    form_data["TotalCharges"],
                    form_data["InternetService"],
                    form_data["PaymentMethod"],
                    pred,
                ),
            )
            customer_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO predictions (customer_id, prediction, probability, risk_level) 
                VALUES (?, ?, ?, ?)
            """,
                (customer_id, pred, prob, risk),
            )
            conn.commit()
        finally:
            conn.close()

        if prob >= 70.0:
            rec_offer = "25% Annual Contract Switch Discount"
            rec_discount = 25.0
            theme_color = "danger"
        elif prob >= 50.0:
            rec_offer = "Free Tech Support & 15% Plan Discount"
            rec_discount = 15.0
            theme_color = "warning"
        else:
            rec_offer = "Loyalty Bill Credit (10% Reward)"
            rec_discount = 10.0
            theme_color = "success"

        result = {
            "customer_id": customer_id,
            "prediction": pred,
            "probability": prob,
            "risk_level": risk,
            "theme_color": theme_color,
            "rec_offer": rec_offer,
            "rec_discount": rec_discount,
            "form": form_data,
        }

    return render_template("index.html", result=result)


# ----------------- Batch Prediction (CSV / Excel Upload) -----------------


@app.route("/batch_predict", methods=["GET", "POST"])
def batch_predict():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        file = request.files.get("file")
        if not file or not (
            file.filename.endswith(".csv")
            or file.filename.endswith(".xls")
            or file.filename.endswith(".xlsx")
        ):
            flash("Please upload a valid CSV or Excel file.", "danger")
            return redirect(url_for("batch_predict"))

        conn = None
        try:
            df = (
                pd.read_csv(file)
                if file.filename.endswith(".csv")
                else pd.read_excel(file)
            )
            processed_count, high_risk_count = 0, 0

            conn = get_db_connection()
            cursor = conn.cursor()

            for _, row in df.iterrows():
                tenure = int(row.get("tenure", row.get("Tenure", 1)))
                monthly = float(
                    row.get("monthly_charges", row.get("MonthlyCharges", 0.0))
                )
                total = float(row.get("total_charges", row.get("TotalCharges", 0.0)))
                contract = str(
                    row.get("contract", row.get("Contract", "Month-to-month"))
                )
                internet = str(
                    row.get("internet_service", row.get("InternetService", "DSL"))
                )
                payment = str(
                    row.get(
                        "payment_method",
                        row.get("PaymentMethod", "Electronic check"),
                    )
                )

                row_dict = {
                    "tenure": tenure,
                    "MonthlyCharges": monthly,
                    "TotalCharges": total,
                    "Contract": contract,
                    "InternetService": internet,
                    "PaymentMethod": payment,
                }

                prob, risk, pred = calculate_churn_risk(row_dict)

                cursor.execute(
                    """
                    INSERT INTO customers 
                    (tenure, contract, monthly_charges, total_charges, internet_service, payment_method, churn) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        tenure,
                        contract,
                        monthly,
                        total,
                        internet,
                        payment,
                        pred,
                    ),
                )
                cust_id = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT INTO predictions (customer_id, prediction, probability, risk_level) 
                    VALUES (?, ?, ?, ?)
                """,
                    (cust_id, pred, prob, risk),
                )

                processed_count += 1
                if risk == "High Risk":
                    high_risk_count += 1

            conn.commit()
            flash(
                f"Batch complete! Processed {processed_count} records ({high_risk_count} High Risk alerts logged).",
                "success",
            )
            return redirect(url_for("customers"))
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Error processing batch file: {e}", "danger")
        finally:
            if conn:
                conn.close()

    return render_template("batch_predict.html")


# ----------------- Dashboard & Reporting -----------------


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        churn_count = conn.execute(
            "SELECT COUNT(*) FROM predictions WHERE risk_level = 'High Risk'"
        ).fetchone()[0]
        non_churn_count = total_customers - churn_count
        churn_rate = (
            round((churn_count / total_customers) * 100, 2)
            if total_customers > 0
            else 0.0
        )

        avg_monthly_res = conn.execute(
            "SELECT AVG(monthly_charges) FROM customers"
        ).fetchone()[0]
        avg_monthly = round(avg_monthly_res, 2) if avg_monthly_res else 0.0

        contract_types = ["Month-to-month", "One year", "Two year"]
        contract_churned, contract_retained = [], []

        for c_type in contract_types:
            ch = conn.execute(
                """
                SELECT COUNT(*) FROM customers c
                JOIN predictions p ON c.customer_id = p.customer_id
                WHERE c.contract = ? AND p.risk_level = 'High Risk'
            """,
                (c_type,),
            ).fetchone()[0]

            ret = conn.execute(
                """
                SELECT COUNT(*) FROM customers c
                JOIN predictions p ON c.customer_id = p.customer_id
                WHERE c.contract = ? AND p.risk_level != 'High Risk'
            """,
                (c_type,),
            ).fetchone()[0]

            contract_churned.append(ch)
            contract_retained.append(ret)
    finally:
        conn.close()

    return render_template(
        "dashboard.html",
        total_customers=total_customers,
        churn_count=churn_count,
        non_churn_count=non_churn_count,
        churn_rate=churn_rate,
        avg_monthly=avg_monthly,
        contract_labels=contract_types,
        contract_churned=contract_churned,
        contract_retained=contract_retained,
    )


@app.route("/model_metrics")
def model_metrics():
    if "user_id" not in session:
        return redirect(url_for("login"))

    feature_names = []
    feature_importances = []

    if os.path.exists(MODEL_PATH) and os.path.exists(COLUMNS_PATH):
        try:
            model = joblib.load(MODEL_PATH)
            columns = joblib.load(COLUMNS_PATH)

            if hasattr(model, "feature_importances_"):
                pairs = sorted(
                    zip(
                        columns,
                        [
                            round(float(val) * 100, 2)
                            for val in model.feature_importances_
                        ],
                    ),
                    key=lambda x: x[1],
                    reverse=True,
                )
                top_pairs = pairs[:10]
                feature_names = [p[0] for p in top_pairs]
                feature_importances = [p[1] for p in top_pairs]
        except Exception as e:
            print(f"Error reading model importances: {e}")

    if not feature_names:
        feature_names = [
            "Contract_Month-to-month",
            "tenure",
            "MonthlyCharges",
            "TotalCharges",
            "InternetService_Fiber optic",
            "PaymentMethod_Electronic check",
            "TechSupport_No",
            "OnlineSecurity_No",
            "Contract_Two year",
            "PaperlessBilling_Yes",
        ]
        feature_importances = [24.5, 21.0, 15.8, 12.4, 8.2, 5.6, 4.3, 3.5, 2.7, 2.0]

    return render_template(
        "metrics.html",
        feature_names=feature_names,
        feature_importances=feature_importances,
    )


# ----------------- Customer Directory & Delete Action -----------------


@app.route("/customers")
def customers():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        customers_data = conn.execute("""
            SELECT c.*, p.risk_level, p.probability 
            FROM customers c 
            LEFT JOIN predictions p ON c.customer_id = p.customer_id 
            ORDER BY c.customer_id DESC
        """).fetchall()
    finally:
        conn.close()

    augmented_customers = []
    for c in customers_data:
        c_dict = dict(c)
        prob = float(c_dict.get("probability") or 0.0)

        if prob >= 70.0:
            c_dict["recommended_offer"] = "25% Annual Contract Switch Discount"
            c_dict["recommended_discount"] = 25.0
            c_dict["offer_badge"] = "danger"
        elif prob >= 50.0:
            c_dict["recommended_offer"] = "Free Tech Support & 15% Plan Discount"
            c_dict["recommended_discount"] = 15.0
            c_dict["offer_badge"] = "warning"
        else:
            c_dict["recommended_offer"] = "Loyalty Bill Credit (10% Reward)"
            c_dict["recommended_discount"] = 10.0
            c_dict["offer_badge"] = "success"

        augmented_customers.append(c_dict)

    return render_template(
        "customers.html",
        customers=augmented_customers,
        user_role=session.get("role", "agent"),
    )


@app.route("/delete_customer/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    """Deletes a customer and all cascading foreign key dependencies cleanly."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM retention_campaigns WHERE customer_id = ?", (customer_id,))
        cursor.execute("DELETE FROM predictions WHERE customer_id = ?", (customer_id,))
        cursor.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
        conn.commit()
        flash(f"Customer #{customer_id} and all related records have been deleted.", "warning")
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Error deleting customer #{customer_id}: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("customers"))


@app.route("/export_customers")
def export_customers():
    if "user_id" not in session:
        return redirect(url_for("login"))

    risk_filter = request.args.get("risk")
    conn = get_db_connection()

    try:
        query = """
            SELECT c.customer_id, c.tenure, c.contract, c.monthly_charges, c.total_charges, 
                   c.internet_service, c.payment_method, c.churn, p.probability, p.risk_level
            FROM customers c
            LEFT JOIN predictions p ON c.customer_id = p.customer_id
        """
        if risk_filter:
            query += " WHERE p.risk_level = ?"
            rows = conn.execute(query, (risk_filter,)).fetchall()
        else:
            rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    df = pd.DataFrame([dict(row) for row in rows])
    csv_data = df.to_csv(index=False)
    filename = (
        "churnguard_high_risk_report.csv"
        if risk_filter
        else "churnguard_all_customers_report.csv"
    )

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"},
    )


@app.route("/export_executive_report")
def export_executive_report():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        total_cust = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        high_risk_cust = conn.execute(
            "SELECT COUNT(*) FROM predictions WHERE risk_level = 'High Risk'"
        ).fetchone()[0]
        churn_pct = (
            round((high_risk_cust / total_cust) * 100, 2) if total_cust > 0 else 0.0
        )

        mrr_res = conn.execute("""
            SELECT SUM(c.monthly_charges) FROM customers c
            JOIN predictions p ON c.customer_id = p.customer_id
            WHERE p.risk_level = 'High Risk'
        """).fetchone()[0]
        mrr_at_risk = round(mrr_res, 2) if mrr_res else 0.0

        avg_res = conn.execute(
            "SELECT AVG(monthly_charges) FROM customers"
        ).fetchone()[0]
        avg_monthly = round(avg_res, 2) if avg_res else 0.0

        kpi_df = pd.DataFrame([
            {"Metric": "Total Analyzed Customers", "Value": total_cust},
            {"Metric": "High Churn Risk Customers", "Value": high_risk_cust},
            {"Metric": "Overall Churn Risk Rate", "Value": f"{churn_pct}%"},
            {"Metric": "Monthly Recurring Revenue (MRR) at Risk", "Value": f"₹{mrr_at_risk}"},
            {"Metric": "Average Customer Monthly Charges", "Value": f"₹{avg_monthly}"},
            {"Metric": "Primary ML Algorithm", "Value": "Random Forest Classifier (100 Trees)"},
        ])

        contract_query = """
            SELECT c.contract AS Contract_Type,
                   COUNT(c.customer_id) AS Total_Accounts,
                   SUM(CASE WHEN p.risk_level = 'High Risk' THEN 1 ELSE 0 END) AS High_Risk_Count,
                   ROUND(AVG(c.monthly_charges), 2) AS Avg_Monthly_Charges
            FROM customers c
            LEFT JOIN predictions p ON c.customer_id = p.customer_id
            GROUP BY c.contract
        """
        contract_df = pd.DataFrame([dict(r) for r in conn.execute(contract_query).fetchall()])

        high_risk_query = """
            SELECT c.customer_id AS Customer_ID, c.tenure AS Tenure_Months, c.contract AS Contract,
               c.monthly_charges AS Monthly_Charges_INR, c.internet_service AS Internet_Service,
               c.payment_method AS Payment_Method, p.probability AS Churn_Probability_Pct, p.risk_level AS Risk_Level
            FROM customers c
            JOIN predictions p ON c.customer_id = p.customer_id
            WHERE p.risk_level = 'High Risk'
            ORDER BY p.probability DESC
        """
        high_risk_df = pd.DataFrame([dict(r) for r in conn.execute(high_risk_query).fetchall()])

        camp_query = """
            SELECT rc.campaign_id AS Campaign_ID, rc.customer_id AS Customer_ID,
               rc.offer_type AS Offer_Description, rc.discount_percent AS Discount_Pct,
               rc.sent_at AS Dispatched_Timestamp, rc.status AS Delivery_Status
            FROM retention_campaigns rc
            ORDER BY rc.campaign_id DESC
        """
        camp_df = pd.DataFrame([dict(r) for r in conn.execute(camp_query).fetchall()])
    finally:
        conn.close()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        kpi_df.to_excel(writer, sheet_name="Executive Summary", index=False)
        contract_df.to_excel(writer, sheet_name="Contract Breakdown", index=False)
        high_risk_df.to_excel(writer, sheet_name="High Risk Customers", index=False)
        camp_df.to_excel(writer, sheet_name="Campaigns Log", index=False)

    output.seek(0)
    return send_file(
        output,
        download_name="ChurnGuard_Executive_Retention_Report.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ----------------- Campaigns -----------------


@app.route("/campaigns")
def campaigns():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    try:
        campaigns_data = conn.execute("""
            SELECT rc.*, p.risk_level 
            FROM retention_campaigns rc 
            LEFT JOIN predictions p ON rc.customer_id = p.customer_id 
            ORDER BY rc.campaign_id DESC
        """).fetchall()
    finally:
        conn.close()

    return render_template("campaigns.html", campaigns=campaigns_data)


@app.route("/send_campaign/<int:customer_id>", methods=["POST"])
def send_campaign(customer_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    offer_type = request.form.get("offer_type", "Targeted Retention Discount")
    discount = float(request.form.get("discount_percent", 15.0))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO retention_campaigns (customer_id, offer_type, discount_percent, status) 
            VALUES (?, ?, ?, 'Sent')
        """,
            (customer_id, offer_type, discount),
        )
        conn.commit()
    finally:
        conn.close()

    flash(
        f"Campaign dispatched: '{offer_type}' ({discount}% discount) sent to Customer #{customer_id}.",
        "success",
    )
    return redirect(url_for("campaigns"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=False, host="0.0.0.0", port=port)