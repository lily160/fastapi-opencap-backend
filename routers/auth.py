from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.db import get_db
from config.constants import CODE_CREATE, CODE_SUCCESS, CODE_NO_CONTENT

router = APIRouter()

# 1 用户注册
@router.post("/register", status_code=CODE_CREATE) # 【修改：使用常量代替硬编码201】
def register(db: Session = Depends(get_db)):
    return {"msg": "用户注册接口待实现"}

# 2 用户登录
@router.post("/login")
def login(db: Session = Depends(get_db)):
    return {"msg": "登录接口待实现"}

# 3 刷新Token
@router.post("/refresh")
def refresh_token():
    return {"msg": "刷新令牌待实现"}

# 4 登出
@router.post("/logout", status_code=CODE_NO_CONTENT)
def logout():
    return

# 5 修改密码
@router.put("/password")
def change_password():
    return {"msg": "修改密码待实现"}

# 【新增：忘记密码全套3个接口，无需鉴权，对齐V1.6】
# 6 忘记密码-查询脱敏联系方式
@router.post("/forgot/lookup", status_code=CODE_SUCCESS)
def forgot_lookup():
    return {"msg": "查询脱敏联系方式接口待实现"}

# 7 忘记密码-发送验证码
@router.post("/forgot/send-code", status_code=CODE_SUCCESS)
def forgot_send_code():
    return {"msg": "发送验证码接口待实现"}

# 8 忘记密码-验证码重置密码
@router.post("/forgot/reset", status_code=CODE_SUCCESS)
def forgot_reset():
    return {"msg": "重置密码接口待实现"}