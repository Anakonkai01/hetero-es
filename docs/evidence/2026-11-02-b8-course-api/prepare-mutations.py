import ast,json
from pathlib import Path
root=Path('/home/pc5070ti/projects/heteroes');out=Path(__file__).parent
mutants=[]
def add(name,file,old,new):
 s=(root/file).read_text();assert s.count(old)==1,(name,s.count(old));ast.parse(s.replace(old,new,1));mutants.append(dict(name=name,file=file,old=old,new=new))
f='backend/apps/factory.py';s='backend/services/course.py';a='backend/api/course.py';r='backend/repositories/course.py'
add('course-enabled-without-flag',f,'service == "api" and os.environ.get("HETEROES_COURSE_DEMO", "0") == "1"','service == "api"')
add('course-routes-on-other-roles',f,'service == "api" and os.environ.get("HETEROES_COURSE_DEMO", "0") == "1"','os.environ.get("HETEROES_COURSE_DEMO", "0") == "1"')
add('hello-wire-contract-changed',a,'Hello from App Server!','Hello')
add('secure-accepts-web-client',s,'client_id="flask-app"','client_id="heteroes-web"')
add('secure-decodes-without-signature-or-claims',s,'claims = self.verifier.verify(token)','claims = __import__("jwt").decode(token, options={"verify_signature": False})')
add('secure-does-not-require-bearer-scheme',s,'if scheme.lower() != "bearer" or not token:','if not token:')
add('students-static-empty-response',s,'return rows','return []')
add('students-unbounded-file-size',s,'if len(payload) > _MAX_STUDENTS_BYTES:','if False:')
add('students-object-instead-of-list-allowed',s,'if not isinstance(rows, list):','if False:')
add('students-file-error-detail-exposed',s,'except (OSError, ValueError):\n            raise ServiceError(503, "Course student file is unavailable") from None','except (OSError, ValueError) as error:\n            raise ServiceError(503, str(error)) from None')
add('students-database-error-detail-exposed',s,'except Exception:\n            raise ServiceError(503, "Course student database is unavailable") from None','except Exception as error:\n            raise ServiceError(503, str(error)) from None')
add('students-db-order-reversed',r,'FROM students ORDER BY id','FROM students ORDER BY id DESC')
add('students-db-public-column-changed',r,'SELECT id,student_id,fullname,dob,major','SELECT id,student_id,fullname AS name,dob,major')
add('students-db-response-empty',r,'return [dict(row) for row in rows]','return []')
add('students-db-accepts-other-dialects',s,'if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"} or not url.database:','if not url.database:')
(out/'mutants.json').write_text(json.dumps(mutants,indent=2)+'\n')
print('Prepared',len(mutants),'syntactically valid mutants')
