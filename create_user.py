import sqlite3

DATABASE_NAME = "churnguard.db"

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

# Insert the initial admin user into the users table
cursor.execute('''
    INSERT OR IGNORE INTO users (name, email, password, role)
    VALUES ('Admin User', 'admin@example.com', 'admin123', 'admin')
''')

conn.commit()
conn.close()

print("Success: Admin user is ready! (admin@example.com / admin123)")
