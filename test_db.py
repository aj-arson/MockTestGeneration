import  mysql.connector


db = mysql.connector.connect(
    host='localhost',
    user='Ajay',
    passwd='1234',
    database="testdb"
)

cursor = db.cursor()
# Q1 = "CREATE TABLE MockTest (Test_ID int PRIMARY KEY NOT NULL AUTO_INCREMENT, NUMBER_OF_SETS int, QUESTIONS JSON)"
Q1 =  "select* from mocktest"
cursor.execute(Q1)

print(cursor.fetchone())