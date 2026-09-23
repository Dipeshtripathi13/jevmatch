from core.config import Settings
from core.storage import (
    add_saved_resume,
    list_saved_resumes,
    load_saved_resume,
    remove_saved_resume,
    rename_saved_resume,
)


def test_resume_library_lifecycle(tmp_path):
    settings = Settings(data_dir=tmp_path)
    record = add_saved_resume(b"Jane Doe\nPython engineer", "jane.txt", "Backend", settings)
    assert len(list_saved_resumes(settings)) == 1
    assert load_saved_resume(record.id, settings).name == "Backend"
    renamed = rename_saved_resume(record.id, "Platform", settings)
    assert renamed.name == "Platform"
    remove_saved_resume(record.id, settings)
    assert list_saved_resumes(settings) == []
