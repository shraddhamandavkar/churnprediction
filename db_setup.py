# db_setup.py
import sqlite3

DATABASE_NAME = "churnguard.db"

def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Agent/Admin Users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'agent'
        )
    ''')

    # Customer Profile Records
    cursor.execute('''
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
    ''')

    # Model Predictions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            prediction TEXT,
            probability REAL,
            risk_level TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id) ON DELETE CASCADE
        )
    ''')

    # Retention Offers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS retention_campaigns (
            campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            offer_type TEXT,
            discount_percent REAL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Sent'
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()