"""
Database Schemas for Collaborative Project Management App

Each Pydantic model corresponds to a MongoDB collection. The collection name
is the lowercase class name (e.g., User -> "user").
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl, EmailStr
from datetime import datetime

# ------------------ Core Collections ------------------

class User(BaseModel):
    id: Optional[str] = Field(None, description="Document id as string")
    username: str
    email: EmailStr
    emailVerified: bool = False
    profilePic: Optional[str] = None  # store URL/base64; simple URL for this app
    companyName: Optional[str] = None
    role: Optional[Literal['student','working']] = None
    linkedIn: Optional[HttpUrl] = None
    interests: List[str] = []
    createdAt: Optional[datetime] = None

class Project(BaseModel):
    projectId: Optional[str] = None
    title: str
    description: str
    category: str
    tags: List[str] = []
    attachments: List[str] = []  # urls for images/docs
    createdBy: str  # user id string
    members: List[str] = []  # user id strings
    type: Literal['solo','combined'] = 'solo'
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

class ChatMessage(BaseModel):
    messageId: Optional[str] = None
    projectId: str
    senderId: str
    content: str
    timestamp: Optional[datetime] = None

class CollaborationRequest(BaseModel):
    requestId: Optional[str] = None
    projectId: str
    senderUserId: str
    status: Literal['pending','accepted','rejected'] = 'pending'
    createdAt: Optional[datetime] = None
