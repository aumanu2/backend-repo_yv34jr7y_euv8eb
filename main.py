import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Collaborative Project Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Utilities ---------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


def serialize(doc: dict) -> dict:
    if not doc:
        return doc
    doc["id"] = str(doc.get("_id"))
    doc.pop("_id", None)
    return doc


# --------- Schemas (light, for request bodies) ---------
class UserIn(BaseModel):
    username: str
    email: str
    emailVerified: Optional[bool] = False
    profilePic: Optional[str] = None
    companyName: Optional[str] = None
    role: Optional[str] = None  # student/working
    linkedIn: Optional[str] = None
    interests: List[str] = []


class ProjectIn(BaseModel):
    title: str
    description: str
    category: str
    tags: List[str] = []
    attachments: List[str] = []
    createdBy: str
    members: List[str] = []
    type: Optional[str] = "solo"  # solo/combined


class ChatIn(BaseModel):
    content: str
    senderId: str


class RequestIn(BaseModel):
    projectId: str
    senderUserId: str


# --------- Root & Test ---------
@app.get("/")
def read_root():
    return {"message": "Collaborative Project Management Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# --------- Schema Introspection (optional helper) ---------
@app.get("/schema")
def get_schema_overview():
    return {
        "collections": [
            "user",
            "project",
            "chatmessage",
            "collaborationrequest",
        ]
    }


# --------- Users ---------
@app.get("/api/users")
def list_users():
    users = db["user"].find().limit(100)
    return [serialize(u) for u in users]


@app.post("/api/users")
def create_or_login_user(user: UserIn):
    existing = db["user"].find_one({"email": user.email})
    now = datetime.now(timezone.utc)
    if existing:
        # update profile fields on login
        db["user"].update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "username": user.username,
                    "profilePic": user.profilePic,
                    "companyName": user.companyName,
                    "role": user.role,
                    "linkedIn": user.linkedIn,
                    "interests": user.interests,
                    "updated_at": now,
                }
            },
        )
        updated = db["user"].find_one({"_id": existing["_id"]})
        return serialize(updated)
    else:
        data = user.model_dump()
        data["created_at"] = now
        data["updated_at"] = now
        new_id = db["user"].insert_one(data).inserted_id
        return serialize(db["user"].find_one({"_id": new_id}))


@app.get("/api/users/{user_id}")
def get_user(user_id: str):
    u = db["user"].find_one({"_id": oid(user_id)})
    if not u:
        raise HTTPException(404, "User not found")
    return serialize(u)


@app.put("/api/users/{user_id}")
def update_user(user_id: str, user: UserIn):
    now = datetime.now(timezone.utc)
    res = db["user"].update_one({"_id": oid(user_id)}, {"$set": {**user.model_dump(), "updated_at": now}})
    if res.matched_count == 0:
        raise HTTPException(404, "User not found")
    return serialize(db["user"].find_one({"_id": oid(user_id)}))


@app.post("/api/users/{user_id}/verify_email")
def verify_email(user_id: str):
    db["user"].update_one({"_id": oid(user_id)}, {"$set": {"emailVerified": True}})
    return {"status": "verified"}


# --------- Projects ---------
@app.get("/api/projects")
def list_projects(q: Optional[str] = None, category: Optional[str] = None, interest: Optional[str] = None, creator: Optional[str] = None):
    query = {}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = {"$regex": f"^{category}$", "$options": "i"}
    if interest:
        query["tags"] = {"$regex": interest, "$options": "i"}
    if creator:
        query["createdBy"] = creator
    items = db["project"].find(query).sort("updated_at", -1)
    return [serialize(i) for i in items]


@app.post("/api/projects")
def create_project(p: ProjectIn):
    now = datetime.now(timezone.utc)
    data = p.model_dump()
    data["created_at"] = now
    data["updated_at"] = now
    # Ensure owner is member too
    if p.createdBy and p.createdBy not in data.get("members", []):
        data.setdefault("members", []).append(p.createdBy)
    new_id = db["project"].insert_one(data).inserted_id
    return serialize(db["project"].find_one({"_id": new_id}))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    pr = db["project"].find_one({"_id": oid(project_id)})
    if not pr:
        raise HTTPException(404, "Project not found")
    return serialize(pr)


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, p: ProjectIn):
    now = datetime.now(timezone.utc)
    res = db["project"].update_one({"_id": oid(project_id)}, {"$set": {**p.model_dump(), "updated_at": now}})
    if res.matched_count == 0:
        raise HTTPException(404, "Project not found")
    return serialize(db["project"].find_one({"_id": oid(project_id)}))


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, userId: Optional[str] = None):
    pr = db["project"].find_one({"_id": oid(project_id)})
    if not pr:
        raise HTTPException(404, "Project not found")
    if userId and pr.get("createdBy") != userId:
        raise HTTPException(403, "Only owner can delete")
    db["project"].delete_one({"_id": pr["_id"]})
    # cleanup related
    db["chatmessage"].delete_many({"projectId": project_id})
    db["collaborationrequest"].delete_many({"projectId": project_id})
    return {"deleted": True}


@app.post("/api/projects/{project_id}/join")
def join_project(project_id: str, userId: str):
    pr = db["project"].find_one({"_id": oid(project_id)})
    if not pr:
        raise HTTPException(404, "Project not found")
    if userId in pr.get("members", []):
        return {"joined": True}
    db["project"].update_one({"_id": pr["_id"]}, {"$addToSet": {"members": userId}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    return {"joined": True}


@app.post("/api/projects/{project_id}/leave")
def leave_project(project_id: str, userId: str):
    pr = db["project"].find_one({"_id": oid(project_id)})
    if not pr:
        raise HTTPException(404, "Project not found")
    db["project"].update_one({"_id": pr["_id"]}, {"$pull": {"members": userId}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    return {"left": True}


@app.get("/api/projects/{project_id}/members")
def list_members(project_id: str):
    pr = db["project"].find_one({"_id": oid(project_id)})
    if not pr:
        raise HTTPException(404, "Project not found")
    members = list(db["user"].find({"_id": {"$in": [oid(uid) for uid in pr.get("members", []) if ObjectId.is_valid(uid)]}}))
    return [serialize(u) for u in members]


# --------- Chat ---------
@app.get("/api/projects/{project_id}/chat")
def get_chat(project_id: str, limit: int = 50):
    msgs = db["chatmessage"].find({"projectId": project_id}).sort("timestamp", -1).limit(limit)
    items = [serialize(m) for m in msgs]
    return list(reversed(items))


@app.post("/api/projects/{project_id}/chat")
def post_chat(project_id: str, msg: ChatIn):
    now = datetime.now(timezone.utc)
    data = {"projectId": project_id, "senderId": msg.senderId, "content": msg.content, "timestamp": now}
    new_id = db["chatmessage"].insert_one(data).inserted_id
    inserted = db["chatmessage"].find_one({"_id": new_id})
    # Simulated bot co-creator reply for activity
    if msg.content and msg.content.strip().endswith("?"):
        bot = {
            "projectId": project_id,
            "senderId": "sim-bot",
            "content": "Great question! Let's capture tasks for this and assign owners.",
            "timestamp": datetime.now(timezone.utc),
        }
        db["chatmessage"].insert_one(bot)
    return serialize(inserted)


# --------- Collaboration Requests ---------
@app.post("/api/projects/{project_id}/requests")
def request_collab(project_id: str, r: RequestIn):
    # Ensure single pending per user/project
    existing = db["collaborationrequest"].find_one({"projectId": project_id, "senderUserId": r.senderUserId, "status": "pending"})
    if existing:
        return serialize(existing)
    data = {"projectId": project_id, "senderUserId": r.senderUserId, "status": "pending", "createdAt": datetime.now(timezone.utc)}
    new_id = db["collaborationrequest"].insert_one(data).inserted_id
    return serialize(db["collaborationrequest"].find_one({"_id": new_id}))


@app.get("/api/projects/{project_id}/requests")
def list_requests(project_id: str):
    items = db["collaborationrequest"].find({"projectId": project_id}).sort("createdAt", -1)
    return [serialize(i) for i in items]


class RespondIn(BaseModel):
    decision: str  # accepted/rejected
    ownerId: Optional[str] = None


@app.post("/api/requests/{request_id}/respond")
def respond_request(request_id: str, body: RespondIn):
    req = db["collaborationrequest"].find_one({"_id": oid(request_id)})
    if not req:
        raise HTTPException(404, "Request not found")
    decision = body.decision
    if decision not in ("accepted", "rejected"):
        raise HTTPException(400, "Invalid decision")
    db["collaborationrequest"].update_one({"_id": req["_id"]}, {"$set": {"status": decision}})
    if decision == "accepted":
        db["project"].update_one({"_id": oid(req["projectId"])}, {"$addToSet": {"members": req["senderUserId"]}, "$set": {"updated_at": datetime.now(timezone.utc)}})
    return {"status": decision}


# --------- Recommendations ---------
@app.get("/api/recommendations/{user_id}")
def recommendations(user_id: str, limit: int = 6):
    user = db["user"].find_one({"_id": oid(user_id)})
    if not user:
        raise HTTPException(404, "User not found")
    interests = user.get("interests", [])
    if not interests:
        items = db["project"].find().sort("updated_at", -1).limit(limit)
        return [serialize(i) for i in items]
    query = {"$or": [{"category": {"$in": interests}}, {"tags": {"$in": interests}}]}
    items = db["project"].find(query).sort("updated_at", -1).limit(limit)
    return [serialize(i) for i in items]


# --------- Seeding data (5+ simulated users and projects) ---------
@app.post("/api/seed")
def seed():
    existing_users = list(db["user"].find())
    if len(existing_users) < 5:
        sample_users = [
            {"username": "Ava", "email": "ava@example.com", "emailVerified": True, "role": "student", "interests": ["Computer Science", "AI", "Design"]},
            {"username": "Ben", "email": "ben@example.com", "emailVerified": True, "role": "working", "interests": ["Business", "Design"]},
            {"username": "Cara", "email": "cara@example.com", "emailVerified": True, "role": "student", "interests": ["Physics", "Robotics"]},
            {"username": "Dee", "email": "dee@example.com", "emailVerified": False, "role": "working", "interests": ["Research", "Arts"]},
            {"username": "Eli", "email": "eli@example.com", "emailVerified": True, "role": "working", "interests": ["Computer Science", "Business"]},
        ]
        ids = []
        for su in sample_users:
            exists = db["user"].find_one({"email": su["email"]})
            if not exists:
                su["created_at"] = datetime.now(timezone.utc)
                su["updated_at"] = datetime.now(timezone.utc)
                uid = db["user"].insert_one(su).inserted_id
                ids.append(str(uid))
            else:
                ids.append(str(exists["_id"]))
    users = list(db["user"].find())
    if db["project"].count_documents({}) < 5 and users:
        samples = [
            {"title": "Open Source Task Tracker", "description": "Collaborative task tracker web app.", "category": "Computer Science", "tags": ["React", "MongoDB"], "attachments": [], "createdBy": str(users[0]["_id"]), "members": [str(users[0]["_id"])], "type": "combined"},
            {"title": "Design System Kit", "description": "Create a Notion-like neutral design kit.", "category": "Design", "tags": ["UI", "Figma"], "attachments": [], "createdBy": str(users[1]["_id"]), "members": [str(users[1]["_id"])], "type": "combined"},
            {"title": "Physics Lab Simulations", "description": "Interactive physics experiments.", "category": "Physics", "tags": ["Education"], "attachments": [], "createdBy": str(users[2]["_id"]), "members": [str(users[2]["_id"])], "type": "solo"},
            {"title": "Startup Market Research", "description": "Analyze trends and competitors.", "category": "Business", "tags": ["Research"], "attachments": [], "createdBy": str(users[3]["_id"]), "members": [str(users[3]["_id"])], "type": "combined"},
            {"title": "Art & Tech Showcase", "description": "Blend art with interactive tech.", "category": "Arts", "tags": ["Installation"], "attachments": [], "createdBy": str(users[4]["_id"]), "members": [str(users[4]["_id"])], "type": "combined"},
        ]
        for sp in samples:
            now = datetime.now(timezone.utc)
            sp["created_at"] = now
            sp["updated_at"] = now
            db["project"].insert_one(sp)
    return {"seeded": True, "users": len(list(db["user"].find())), "projects": db["project"].count_documents({})}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
