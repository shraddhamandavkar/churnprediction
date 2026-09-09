# train_model.py
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# 1. Load dataset
df = pd.read_csv(r"C:\Users\Admin\Downloads\archive (1)\Telco-Customer-Churn.csv")

# 2. Clean data
if "customerID" in df.columns:
    df = df.drop("customerID", axis=1)

# Convert whitespace/empty values in TotalCharges to numeric
df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce").fillna(0)

# 3. Categorical encoding
df_encoded = pd.get_dummies(df, drop_first=True)

# 4. Features (X) and Target (y)
target_col = "Churn_Yes" if "Churn_Yes" in df_encoded.columns else "Churn"
X = df_encoded.drop(target_col, axis=1)
y = df_encoded[target_col]

if y.dtype == "object":
    y = y.map({"Yes": 1, "No": 0})

# 5. Split and Train
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# 6. Save Model and Column List
joblib.dump(model, "churn_model.pkl")
joblib.dump(list(X.columns), "model_columns.pkl")
print("Saved churn_model.pkl and model_columns.pkl successfully.")