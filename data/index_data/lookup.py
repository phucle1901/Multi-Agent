"""Cache phuongs / loai_jobs / companies → tránh INSERT OR IGNORE lặp lại."""


class Lookup:
    def __init__(self, conn):
        self.cur = conn.cursor()
        self._phuong  = {}
        self._loai    = {}
        self._company = {}

    def get_phuong(self, name: str) -> int:
        if name in self._phuong:
            return self._phuong[name]
        self.cur.execute("INSERT OR IGNORE INTO phuongs (name) VALUES (?)", (name,))
        self.cur.execute("SELECT id FROM phuongs WHERE name = ?", (name,))
        pid = self.cur.fetchone()[0]
        self._phuong[name] = pid
        return pid

    def get_loai(self, name: str) -> int:
        if name in self._loai:
            return self._loai[name]
        self.cur.execute("INSERT OR IGNORE INTO loai_jobs (name) VALUES (?)", (name,))
        self.cur.execute("SELECT id FROM loai_jobs WHERE name = ?", (name,))
        lid = self.cur.fetchone()[0]
        self._loai[name] = lid
        return lid

    def get_company(self, name, size, field, address):
        if not name:
            return None
        if name in self._company:
            return self._company[name]
        self.cur.execute(
            "INSERT OR IGNORE INTO companies (name, size, field, address) "
            "VALUES (?, ?, ?, ?)",
            (name, size, field, address),
        )
        self.cur.execute("SELECT id FROM companies WHERE name = ?", (name,))
        cid = self.cur.fetchone()[0]
        self._company[name] = cid
        return cid
