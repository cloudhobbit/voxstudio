"""Background jobs (batch renders, project renders, exports): one at a time, with progress the app can poll."""
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field


@dataclass
class Job:
    id: str
    kind: str
    total: int
    done: int = 0
    status: str = "queued"          # queued | running | done | failed
    urls: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    error: str = ""
    result: dict = field(default_factory=dict)


class JobManager:
    def __init__(self, log=None):
        self.jobs: dict[str, Job] = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="job")
        self.lock = threading.Lock()
        self.log = log

    def start(self, kind: str, total: int, fn) -> Job:
        """fn(job) does the work and updates job.done / job.urls / job.failed / job.result as it goes."""
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, total=total)
        with self.lock:
            self.jobs[job.id] = job
            if len(self.jobs) > 500:  # keep memory bounded on a long-running server
                for old in list(self.jobs)[:100]:
                    if self.jobs[old].status in ("done", "failed"):
                        del self.jobs[old]

        def run():
            job.status = "running"
            try:
                fn(job)
                job.status = "done"
            except Exception as e:
                job.status, job.error = "failed", str(e)
                if self.log:
                    self.log.error("job %s failed\n%s", job.id, traceback.format_exc())

        self.pool.submit(run)
        return job

    def get(self, job_id: str) -> dict | None:
        job = self.jobs.get(job_id)
        return asdict(job) if job else None
