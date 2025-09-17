import  mysql.connector
import json

db = mysql.connector.connect(
    host='localhost',
    user='Ajay',
    passwd='1234',
    database="testdb"
)

def create_new_test_record(db, cursor, number_of_sets, number_of_questions, questions={}, subject="", standard="", chapter_ids=[], status='QUEUED'):
    Q1 = "INSERT INTO MockTest (number_of_sets, number_of_questions, questions, subject, chapter_ids, standard, status) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    cursor.execute(Q1, (number_of_sets, number_of_questions, questions, subject, chapter_ids, standard, status))
    db.commit()
    print("Inserted into Table")

cursor = db.cursor()
# Q1 = "CREATE TABLE MockTest (test_id int PRIMARY KEY NOT NULL AUTO_INCREMENT, number_of_sets int, questions JSON, generation_status ENUM('CREATED', 'COMPLETED', 'FAILED', 'QUEUED', 'PENDING'))"
# Q1 = "CREATE TABLE ratelimit (system_id int PRIMARY KEY NOT NULL AUTO_INCREMENT, max_requests_per_day int unsigned, remaining_requests_for_today int unsigned)"
# Q1 = "insert into ratelimit (max_requests_per_day, remaining_requests_for_today) values (%s, %s)"
# Q1 = "alter table ratelimit rename column remaining_requests_for_today to requests_used"
# Q1 = "alter table mocktest add column (subject varchar(30) NOT NULL), add column (standard varchar(20) NOT NULL), add column (chapter_ids JSON NOT NULL) "

# cursor.execute(Q1, (10,0))
# db.commit()
# Q1 =  "select * from ratelimit"
Q1 =  "select * from mocktest"
# Q1 =  "show columns from mocktest"
# Q1 = "describe mocktest"
# Q1= "DROP TABLE ratelimit"
cursor.execute(Q1)
# db.commit()

# y = []
for x in cursor:
    print(x)
#     y.append(x[0])
# print(y)