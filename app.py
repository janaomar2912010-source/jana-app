import streamlit as st
import sqlite3, csv, os
from datetime import date
from calendar import monthrange

DB, PATH_FILE = "attendance.db", "export_path.txt"

def q(sql, p=(), fetch=False):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(sql, p)
    con.commit()
    rows = cur.fetchall() if fetch else None
    con.close()
    return rows

# DB tables
q("CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT, class_name TEXT, UNIQUE(name, class_name))")
q("CREATE TABLE IF NOT EXISTS att(student_id INTEGER, day TEXT, status TEXT, UNIQUE(student_id, day))")

def get_path():
    return open(PATH_FILE, "r", encoding="utf-8").read().strip() if os.path.exists(PATH_FILE) else ""

def set_path(p):
    open(PATH_FILE, "w", encoding="utf-8").write(p)

def classes():
    return [r[0] for r in q("SELECT DISTINCT class_name FROM students ORDER BY class_name", fetch=True)]

def load_rows(day, chosen):
    if chosen == "الكل":
        return q("""
            SELECT s.id, s.class_name, s.name, COALESCE(a.status,'A')
            FROM students s LEFT JOIN att a ON a.student_id=s.id AND a.day=?
            ORDER BY s.class_name, s.name
        """, (day,), True)
    return q("""
        SELECT s.id, s.class_name, s.name, COALESCE(a.status,'A')
        FROM students s LEFT JOIN att a ON a.student_id=s.id AND a.day=?
        WHERE s.class_name=?
        ORDER BY s.name
    """, (day, chosen), True)

st.set_page_config(page_title="حضور الطلاب", layout="wide")
st.title("حضور الطلاب (ويب بسيط)")

# Sidebar: date dropdowns + class
today = date.today()
years = list(range(today.year, today.year + 11))
months = list(range(1, 13))

c1, c2, c3, c4 = st.columns([1, 1, 1, 2])

with c1:
    y = st.selectbox("السنة", years, index=0)
with c2:
    m = st.selectbox("الشهر", months, index=today.month - 1)
with c3:
    max_day = monthrange(y, m)[1]
    d_list = list(range(1, max_day + 1))
    d = st.selectbox("اليوم", d_list, index=min(today.day, max_day) - 1)
day_str = f"{y:04d}-{m:02d}-{d:02d}"

with c4:
    all_classes = ["الكل"] + classes()
    chosen = st.selectbox("الصف/الشعبة", all_classes, index=0)

st.write(f"**التاريخ المختار:** {day_str}")

# Import CSV
st.subheader("1) استيراد الطلاب من CSV")
up = st.file_uploader("ارفع ملف CSV يحتوي أعمدة: name, class_name", type=["csv"])
if up:
    try:
        content = up.getvalue().decode("utf-8-sig").splitlines()
        r = csv.DictReader(content)
        added = 0
        for row in r:
            n = (row.get("name") or "").strip()
            c = (row.get("class_name") or "").strip()
            if n and c:
                q("INSERT OR IGNORE INTO students(name, class_name) VALUES(?,?)", (n, c))
                added += 1
        st.success(f"تم الاستيراد ✅ (تمت قراءة {added} صف/سطر)")
        st.rerun()
    except Exception as e:
        st.error(str(e))

# Load table
st.subheader("2) سجل الحضور اليومي")
rows = load_rows(day_str, chosen)
if not rows:
    st.info("لا يوجد طلاب بعد. استورد CSV أولاً.")
    st.stop()

# Editable statuses using session_state
key = f"{day_str}::{chosen}"
if key not in st.session_state:
    st.session_state[key] = {str(sid): ("P" if st == "P" else "A") for sid, _, _, st in rows}

# Quick stats
total = len(rows)
present = sum(1 for sid, _, _, _ in rows if st.session_state[key].get(str(sid), "A") == "P")
absent = total - present
p_pct = (present / total * 100) if total else 0
a_pct = 100 - p_pct if total else 0

st.markdown(
    f"""
**الإحصائيات:**
- حاضر: {present} ({p_pct:.1f}%)
- غائب: {absent} ({a_pct:.1f}%)
- المجموع: {total}
"""
)

# Table UI
for sid, cls, name, _ in rows:
    colA, colB, colC, colD = st.columns([2, 4, 2, 2])
    with colA: st.write(cls)
    with colB: st.write(name)
    with colC:
        cur = st.session_state[key].get(str(sid), "A")
        new = st.radio("الحالة", ["حاضر", "غائب"], index=0 if cur == "P" else 1, horizontal=True, key=f"st_{key}_{sid}")
    with colD:
        st.write("")
    st.session_state[key][str(sid)] = "P" if new == "حاضر" else "A"
    st.divider()

# Save button
if st.button("💾 حفظ الحضور"):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    for sid, _, _, _ in rows:
        st_code = st.session_state[key].get(str(sid), "A")
        cur.execute("""
            INSERT INTO att(student_id, day, status) VALUES(?,?,?)
            ON CONFLICT(student_id, day) DO UPDATE SET status=excluded.status
        """, (int(sid), day_str, st_code))
    con.commit()
    con.close()
    st.success("تم حفظ الحضور ✅")

# Export cumulative CSV
st.subheader("3) تصدير (ملف واحد يتراكم)")
export_path = get_path()
st.write("**ملف التصدير الحالي:**", export_path if export_path else "غير محدد بعد")

new_path = st.text_input("إذا بدك تغيّر مسار ملف التصدير: اكتب مسار كامل ويندوز (مثال: D:\\\\JANA_web\\\\attendance_all_days.csv)")
if st.button("تحديد/تغيير ملف التصدير"):
    if not new_path.strip():
        st.warning("اكتب المسار أولاً.")
    else:
        set_path(new_path.strip())
        st.success("تم حفظ مسار ملف التصدير ✅")

if st.button("⬇️ تصدير وإضافة على نفس الملف"):
    p = get_path()
    if not p:
        st.warning("حدد مسار ملف التصدير أولاً.")
    else:
        file_exists = os.path.exists(p)
        with open(p, "a", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow(["التاريخ", "الصف/الشعبة", "اسم الطالب", "الحالة"])
            for sid, cls, name, _ in rows:
                st_code = st.session_state[key].get(str(sid), "A")
                w.writerow([day_str, cls, name, "حاضر" if st_code == "P" else "غائب"])
        st.success(f"تم التصدير ✅ إلى: {os.path.abspath(p)}")