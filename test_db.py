import  mysql.connector
import json

db = mysql.connector.connect(
    host='localhost',
    user='Ajay',
    passwd='1234',
    database="testdb"
)


# -------------------------------------------------------------------------------
with open("sample_text_books\\telugu.txt", "r", encoding="utf-8") as f2:
    chapter2 = f2.read()

# -------------------------------------------------------------------------------

def create_new_test_record(db, cursor, number_of_sets, number_of_questions, questions={}, Subject="", Class="", chapter_context="", status='QUEUED'):
    Q1 = "INSERT INTO MockTests (number_of_sets, number_of_questions, questions, Subject, chapter_context, Class, status) VALUES (%s, %s, %s, %s, %s, %s, %s)"
    cursor.execute(Q1, (number_of_sets, number_of_questions, questions, Subject, chapter_context, Class, status))
    db.commit()
    print("Inserted into Table")

cursor = db.cursor()
# Q1 = "CREATE TABLE MockTests (TestID int PRIMARY KEY NOT NULL AUTO_INCREMENT, number_of_sets int, questions JSON, generation_status ENUM('CREATED', 'COMPLETED', 'FAILED', 'QUEUED', 'PENDING'))"
# Q1 = "CREATE TABLE ratelimit (system_id int PRIMARY KEY NOT NULL AUTO_INCREMENT, max_requests_per_day int unsigned, remaining_requests_for_today int unsigned)"
# Q1 = "insert into ratelimit (max_requests_per_day, remaining_requests_for_today) values (%s, %s)"
# Q1 = "alter table ratelimit rename column remaining_requests_for_today to requests_used"
# Q1 = "alter table mocktest rename mocktests"
# Q1 = "alter table MockTests add column (Subject varchar(30) NOT NULL), add column (Class varchar(20) NOT NULL), add column (chapter_ids JSON NOT NULL) "
# Q1 = "CREATE TABLE syllabus (chapter_id int unsigned PRIMARY KEY NOT NULL AUTO_INCREMENT, Subject varchar(30), Class varchar(20), chapter_text TEXT)"
# Q1 = "insert into syllabus (Subject, Class, chapter_text) values (%s, %s, %s)"

# cursor.execute(Q1, (10,0))
# db.commit()
# Q1 =  "select * from ratelimit"
# Q1 =  "select chapter_id, Subject from syllabus"
# Q1 =  "select * from MockTests"
# Q1 =  "select * from MockTests where TestID=8"
# Q1 = "describe mocktests"
# Q1 = "alter table mocktests rename column chapter_ids to chapter_context"
# Q1 = "alter table mocktests modify column chapter_context LONGTEXT"
# Q1= "DROP TABLE ratelimit"
# cursor.execute(Q1, ("telugu", "10", chapter2))
# q = "truncate table MockTests"
Q1 = "select generation_status from MockTests"
# Q1 = "show tables"
# cursor.execute(q)
# db.commit()
cursor.execute(Q1)
# db.commit()

# y = []
for x in cursor:
    print(x)
#     y.append(x[0])
# print(y)