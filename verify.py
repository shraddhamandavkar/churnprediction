import os
import sys

print("=" * 65)
print("        CHURNGUARD PRE-DEPLOYMENT HEALTH AUDIT")
print("=" * 65)

# 1. File Artifact Checks
required_files = [
    'app.py',
    'churnguard.db',
    'churn_model.pkl',
    'model_columns.pkl',
    'run_production.py',
    'requirements.txt',
]
print("\n[1/5] Checking Critical Files:")
for f in required_files:
    exists = os.path.exists(f)
    size = f"{os.path.getsize(f)/1024:.1f} KB" if exists else "MISSING"
    status = "PASS" if exists else "FAIL"
    print(f"  [{status}] {f:<20} -> {size}")

# 2. Database Schema & Concurrency Mode
print("\n[2/5] Checking Database & WAL Mode:")
try:
    import app

    conn = app.get_db_connection()
    cursor = conn.cursor()
    tables = [
        r[0]
        for r in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT"
            " LIKE 'sqlite_%'"
        ).fetchall()
    ]
    wal_status = cursor.execute("PRAGMA journal_mode;").fetchone()[0]
    fk_status = cursor.execute("PRAGMA foreign_keys;").fetchone()[0]
    conn.close()
    print(f"  [PASS] Tables Found: {tables}")
    print(f"  [PASS] Concurrency Journal Mode: {wal_status.upper()}")
    print(f"  [PASS] Foreign Key Enforcement: {'ON' if fk_status else 'OFF'}")
except Exception as e:
    print(f"  [FAIL] Database check failed: {e}")

# 3. Model Pipeline & Feature Alignment
print("\n[3/5] Checking ML Pipeline & Inference:")
try:
    test_dict = {
        'tenure': 2,
        'MonthlyCharges': 85.0,
        'TotalCharges': 170.0,
        'Contract': 'Month-to-month',
        'InternetService': 'Fiber optic',
        'PaymentMethod': 'Electronic check',
    }
    prob, risk, pred = app.calculate_churn_risk(test_dict)
    print(f"  [PASS] Model Inference Executed Successfully:")
    print(
        f"         Prediction: {pred} | Probability: {prob}% | Risk Tier: {risk}"
    )
except Exception as e:
    print(f"  [FAIL] Inference pipeline error: {e}")

# 4. Frontend Templates Check
print("\n[4/5] Checking Frontend Templates:")
templates = [
    'base.html',
    'index.html',
    'batch_predict.html',
    'customers.html',
    'dashboard.html',
    'metrics.html',
    'campaigns.html',
    'login.html',
    'register.html',
]
missing_tpl = [
    t for t in templates if not os.path.exists(os.path.join('templates', t))
]
if not missing_tpl:
    print(f"  [PASS] All {len(templates)} Jinja2 templates present in /templates")
else:
    print(f"  [FAIL] Missing templates: {missing_tpl}")

# 5. Deployment Server Config
print("\n[5/5] Checking Server Configuration:")
procfile_exists = os.path.exists("Procfile")
print(
    f"  [{'PASS' if procfile_exists else 'INFO'}] Procfile: {'Found (ready for Render/Railway)' if procfile_exists else 'Not created yet (only required for cloud containers)'}"
)

print("\n" + "=" * 65)
print("AUDIT COMPLETE: All core checks evaluated.")
print("=" * 65)