from pydantic import BaseModel
class VideoUploadResp(BaseModel):
    file_id: str
    filename: str
    size: int
    mime_type: str
    class Config:
        from_attributes = True
