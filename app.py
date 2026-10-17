from datetime import datetime, timedelta, timezone
from typing import Optional
import os

from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt, JWTError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'twincity.db')}")
SECRET_KEY = os.getenv("TWINCITY_SECRET_KEY", "CHANGE_THIS_DEMO_SECRET_BEFORE_DEPLOYMENT_32CHARS_MIN")
ALGORITHM = "HS256"
TOKEN_HOURS = 2

engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="citizen", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Asset(Base):
    __tablename__ = "assets"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    asset_type = Column(String(60), nullable=False)
    latitude = Column(Float, default=19.0760)
    longitude = Column(Float, default=72.8777)
    status = Column(String(30), default="normal")
    sensitive = Column(Boolean, default=False)
    description = Column(Text, default="")

class Layer(Base):
    __tablename__ = "layers"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    unit = Column(String(30), default="")
    source = Column(String(120), default="Demo data")
    value = Column(Float, default=0)
    enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    title = Column(String(160), nullable=False)
    severity = Column(String(20), default="medium")
    message = Column(Text, default="")
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    acknowledged_by = Column(String(255), nullable=True)

class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, default="")
    parameter = Column(String(80), default="traffic_reduction_percent")
    value = Column(Float, default=10)
    status = Column(String(30), default="created")
    result = Column(Text, default="")
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    actor = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False)
    details = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)
app = FastAPI(title="TwinCity Portal API", version="0.1.0", description="Python demonstration implementation for the TwinCity Portal SRS")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

ROLE_LEVEL = {"citizen": 1, "planner": 2, "operator": 2, "data_steward": 3, "admin": 4}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def audit(db: Session, actor: str, action: str, details: str = ""):
    db.add(AuditEvent(actor=actor, action=action, details=details))
    db.commit()

def seed_demo_data():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "admin@twincity.local").first():
            db.add(User(email="admin@twincity.local", password_hash=pwd_context.hash("ChangeMe123!"), role="admin"))
        if db.query(Asset).count() == 0:
            db.add_all([
                Asset(name="Central Hospital", asset_type="hospital", latitude=19.076, longitude=72.8777, status="normal", description="Public demonstration asset"),
                Asset(name="Water Treatment Plant", asset_type="water", latitude=19.09, longitude=72.89, status="warning", sensitive=True, description="Restricted infrastructure; hidden from citizen role"),
                Asset(name="Metro Station A", asset_type="transport", latitude=19.065, longitude=72.869, status="normal", description="Transit asset"),
                Asset(name="Solar Facility", asset_type="energy", latitude=19.11, longitude=72.91, status="normal", description="Renewable energy demonstration asset"),
            ])
        if db.query(Layer).count() == 0:
            db.add_all([
                Layer(name="Traffic", unit="vehicles/min", value=68), Layer(name="Energy", unit="MW", value=42.5),
                Layer(name="Water", unit="ML/day", value=81.2), Layer(name="Air Quality", unit="AQI", value=74),
                Layer(name="Noise", unit="dB", value=57), Layer(name="Incidents", unit="events", value=3),
            ])
        if db.query(Alert).count() == 0:
            db.add_all([Alert(title="Traffic congestion near Central Junction", severity="high", message="Demo alert: traffic flow is above the normal threshold."), Alert(title="Air quality advisory", severity="medium", message="Demo alert: air quality requires monitoring.")])
        db.commit()
    finally:
        db.close()
seed_demo_data()

class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # role intentionally omitted: callers cannot assign their own role

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class ScenarioInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    parameter: str = "traffic_reduction_percent"
    value: float = Field(ge=0, le=100)

class AssetInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    asset_type: str = Field(min_length=2, max_length=60)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    status: str = "normal"
    sensitive: bool = False
    description: str = ""

def create_token(user: User):
    now = datetime.now(timezone.utc)
    payload = {"sub": user.email, "exp": now + timedelta(hours=TOKEN_HOURS), "iat": now}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def current_user(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user

def require_roles(*roles):
    def dependency(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dependency

@app.get("/")
def home():
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))

@app.get("/health")
def health():
    return {"status": "ok", "service": "TwinCity Portal API", "time_utc": datetime.now(timezone.utc).isoformat()}

@app.post("/api/auth/register", status_code=201)
def register(body: RegisterInput, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Unable to register with these details")
    if not any(c.islower() for c in body.password) or not any(c.isupper() for c in body.password) or not any(c.isdigit() for c in body.password):
        raise HTTPException(status_code=422, detail="Password must include uppercase, lowercase and numeric characters")
    user = User(email=email, password_hash=pwd_context.hash(body.password), role="citizen")
    db.add(user); db.commit(); db.refresh(user)
    audit(db, user.email, "register", "Default role assigned: citizen")
    return {"message": "Registration successful", "email": user.email, "role": user.role}

@app.post("/api/auth/login")
def login(body: LoginInput, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.query(User).filter(User.email == email).first()
    now = datetime.now(timezone.utc)
    if user and user.locked_until:
        locked = user.locked_until
        if locked.tzinfo is None: locked = locked.replace(tzinfo=timezone.utc)
        if locked > now:
            raise HTTPException(status_code=423, detail="Unable to sign in at this time")
    if not user or not pwd_context.verify(body.password, user.password_hash):
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
            db.commit(); audit(db, email, "failed_login", "Invalid credentials")
        # Same public error for unknown email and wrong password
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.enabled:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.failed_attempts = 0; user.locked_until = None; db.commit()
    audit(db, email, "login", "Successful sign-in")
    return {"access_token": create_token(user), "token_type": "bearer", "role": user.role, "email": user.email}

@app.post("/api/auth/logout")
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, user.email, "logout", "Client must discard bearer token")
    return {"message": "Signed out; clear the token in the client"}

@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "role": user.role}

@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"role": user.role, "assets": db.query(Asset).count(), "layers": db.query(Layer).count(), "open_alerts": db.query(Alert).filter(Alert.acknowledged == False).count(), "scenarios": db.query(Scenario).count(), "as_of": datetime.now(timezone.utc).isoformat()}

@app.get("/api/assets")
def list_assets(user: User = Depends(current_user), db: Session = Depends(get_db), search: str = ""):
    q = db.query(Asset)
    if user.role == "citizen": q = q.filter(Asset.sensitive == False)
    if search: q = q.filter(Asset.name.ilike(f"%{search}%"))
    return [{"id": a.id, "name": a.name, "asset_type": a.asset_type, "latitude": a.latitude, "longitude": a.longitude, "status": a.status, "description": a.description} for a in q.order_by(Asset.id).all()]

@app.post("/api/assets", status_code=201)
def create_asset(body: AssetInput, user: User = Depends(require_roles("admin", "data_steward")), db: Session = Depends(get_db)):
    asset = Asset(**body.model_dump()); db.add(asset); db.commit(); db.refresh(asset)
    audit(db, user.email, "asset_created", f"asset_id={asset.id}")
    return {"id": asset.id, "name": asset.name}

@app.get("/api/layers")
def list_layers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": x.id, "name": x.name, "unit": x.unit, "source": x.source, "value": x.value, "enabled": x.enabled, "updated_at": (x.updated_at.isoformat() if x.updated_at else None)} for x in db.query(Layer).order_by(Layer.id).all()]

@app.patch("/api/layers/{layer_id}/toggle")
def toggle_layer(layer_id: int, user: User = Depends(require_roles("planner", "operator", "data_steward", "admin")), db: Session = Depends(get_db)):
    layer = db.query(Layer).filter(Layer.id == layer_id).first()
    if not layer: raise HTTPException(status_code=404, detail="Layer not found")
    layer.enabled = not layer.enabled; layer.updated_at = datetime.now(timezone.utc); db.commit()
    audit(db, user.email, "layer_toggled", f"layer_id={layer_id}, enabled={layer.enabled}")
    return {"id": layer.id, "enabled": layer.enabled}

@app.get("/api/alerts")
def list_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": a.id, "title": a.title, "severity": a.severity, "message": a.message, "acknowledged": a.acknowledged, "created_at": a.created_at.isoformat() if a.created_at else None} for a in db.query(Alert).order_by(Alert.acknowledged, Alert.id.desc()).all()]

@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, user: User = Depends(require_roles("operator", "admin")), db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert: raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True; alert.acknowledged_by = user.email; db.commit()
    audit(db, user.email, "alert_acknowledged", f"alert_id={alert_id}")
    return {"id": alert.id, "acknowledged": True}

@app.get("/api/scenarios")
def list_scenarios(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name, "description": s.description, "parameter": s.parameter, "value": s.value, "status": s.status, "result": s.result, "created_at": s.created_at.isoformat() if s.created_at else None} for s in db.query(Scenario).order_by(Scenario.id.desc()).all()]

@app.post("/api/scenarios", status_code=201)
def create_scenario(body: ScenarioInput, user: User = Depends(require_roles("planner", "admin")), db: Session = Depends(get_db)):
    # Replace this deterministic demonstration with an adapter to the real simulation service.
    result = f"Demo simulation: {body.parameter} set to {body.value:g}. This is an illustrative estimate, not a live city prediction."
    scenario = Scenario(name=body.name, description=body.description, parameter=body.parameter, value=body.value, status="completed_demo", result=result, created_by=user.email)
    db.add(scenario); db.commit(); db.refresh(scenario)
    audit(db, user.email, "scenario_created", f"scenario_id={scenario.id}")
    return {"id": scenario.id, "status": scenario.status, "result": scenario.result}

@app.get("/api/admin/users")
def admin_users(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "role": u.role, "enabled": u.enabled, "created_at": u.created_at.isoformat() if u.created_at else None} for u in db.query(User).order_by(User.id).all()]

@app.get("/api/admin/audit")
def admin_audit(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return [{"id": a.id, "actor": a.actor, "action": a.action, "details": a.details, "created_at": a.created_at.isoformat() if a.created_at else None} for a in db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(200).all()]
