import mysql.connector

try:
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='50060010',
        database='smart_parking'
    )
    print("✅ Database connection successful!")
    
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"✅ Found {len(tables)} tables")
    
    for table in tables:
        print(f"  - {table[0]}")
    
    cursor.close()
    conn.close()
    
except mysql.connector.Error as err:
    print(f"❌ Error: {err}")
    print("\nPossible fixes:")
    print("1. Check MySQL is running")
    print("2. Verify password is correct")
    print("3. Ensure database 'smart_parking' exists")