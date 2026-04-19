"""
scheduler.py
────────────
Conflict detection engine + seed helpers for JKUAT Smart Scheduler.
"""

from models import db, Lecture, Room, School, Programme, Course, Notification, Enrollment


# ─────────────────────────────────────────────
# CONFLICT DETECTION
# ─────────────────────────────────────────────

def get_available_rooms(day: str, start_time, end_time, exclude_lecture_id: int = None):
    """
    Return Room objects that are FREE for the given day + time window.
    Uses the standard interval-overlap formula:
        existing.start < requested.end  AND  existing.end > requested.start
    """
    conflict_q = db.session.query(Lecture.room_id).filter(
        Lecture.day        == day,
        Lecture.start_time <  end_time,
        Lecture.end_time   >  start_time,
    )
    if exclude_lecture_id:
        conflict_q = conflict_q.filter(Lecture.id != exclude_lecture_id)

    booked_ids = [r[0] for r in conflict_q.all()]

    return Room.query.filter(
        Room.is_active == True,
        ~Room.id.in_(booked_ids) if booked_ids else True,
    ).order_by(Room.capacity.asc()).all()


def check_lecturer_conflict(lecturer_id: int, day: str, start_time, end_time,
                             exclude_lecture_id: int = None) -> bool:
    """Return True if lecturer has an overlapping lecture (= conflict exists)."""
    q = Lecture.query.filter(
        Lecture.lecturer_id == lecturer_id,
        Lecture.day         == day,
        Lecture.start_time  <  end_time,
        Lecture.end_time    >  start_time,
    )
    if exclude_lecture_id:
        q = q.filter(Lecture.id != exclude_lecture_id)
    return q.first() is not None


# ─────────────────────────────────────────────
# NOTIFICATION DISPATCH
# ─────────────────────────────────────────────

def notify_enrolled_students(lecture):
    """
    Create a Notification row for every student enrolled in the lecture's course.
    Called immediately after a Lecture is saved (before final commit).
    """
    course    = lecture.course
    room      = lecture.room_ref
    start_str = lecture.start_time.strftime('%H:%M')
    end_str   = lecture.end_time.strftime('%H:%M')

    message = (
        f"📅 New lecture scheduled: {course.code} — {course.name} | "
        f"{lecture.day} {start_str}–{end_str} | Room: {room.name}"
    )

    enrollments = Enrollment.query.filter_by(course_id=course.id).all()

    notifications = [
        Notification(
            user_id    = e.student_id,
            lecture_id = lecture.id,
            message    = message,
            is_read    = False,
        )
        for e in enrollments
    ]

    db.session.add_all(notifications)
    return len(notifications)   # return count for flash message


# ─────────────────────────────────────────────
# SEED — ROOMS
# ─────────────────────────────────────────────

def seed_rooms():
    if Room.query.count() > 0:
        print("Rooms already seeded."); return

    rooms = [
        Room(name="LT1",   capacity=200, room_type="lecture_hall", building="Main Block"),
        Room(name="LT2",   capacity=200, room_type="lecture_hall", building="Main Block"),
        Room(name="LT3",   capacity=150, room_type="lecture_hall", building="Science Block"),
        Room(name="LT4",   capacity=150, room_type="lecture_hall", building="Science Block"),
        Room(name="LT5",   capacity=100, room_type="lecture_hall", building="Engineering Block"),
        Room(name="LT6",   capacity=100, room_type="lecture_hall", building="Engineering Block"),
        Room(name="Lab 1", capacity=40,  room_type="lab",          building="ICT Block"),
        Room(name="Lab 2", capacity=40,  room_type="lab",          building="ICT Block"),
        Room(name="Lab 3", capacity=35,  room_type="lab",          building="ICT Block"),
        Room(name="Lab 4", capacity=35,  room_type="lab",          building="Science Block"),
        Room(name="SR1",   capacity=30,  room_type="seminar",      building="Main Block"),
        Room(name="SR2",   capacity=30,  room_type="seminar",      building="Main Block"),
        Room(name="SR3",   capacity=25,  room_type="seminar",      building="Engineering Block"),
    ]
    db.session.add_all(rooms)
    db.session.commit()
    print(f"✅ Seeded {len(rooms)} rooms.")


# ─────────────────────────────────────────────
# SEED — SCHOOLS & PROGRAMMES
# ─────────────────────────────────────────────

def seed_schools_and_programmes():
    if School.query.count() > 0:
        print("Schools already seeded."); return

    data = [
        {
            'name': 'School of Computing and Information Technology',
            'code': 'SCIT',
            'description': 'Computing, IT and related disciplines.',
            'programmes': [
                {'name': 'Bachelor of Science in Information Technology', 'code': 'BIT',  'duration': 4},
                {'name': 'Bachelor of Business Information Technology',   'code': 'BBIT', 'duration': 4},
                {'name': 'Diploma in Information Technology',             'code': 'DIT',  'duration': 3},
            ],
        },
        {
            'name': 'School of Engineering',
            'code': 'ENG',
            'description': 'Engineering and technology programmes.',
            'programmes': [
                {'name': 'Bachelor of Science in Civil Engineering',       'code': 'BCE',  'duration': 5},
                {'name': 'Bachelor of Science in Electrical Engineering',  'code': 'BEE',  'duration': 5},
                {'name': 'Bachelor of Science in Mechanical Engineering',  'code': 'BME',  'duration': 5},
            ],
        },
        {
            'name': 'School of Health Sciences',
            'code': 'SHS',
            'description': 'Medicine, nursing and health-related programmes.',
            'programmes': [
                {'name': 'Bachelor of Medicine and Bachelor of Surgery', 'code': 'MBChB', 'duration': 6},
                {'name': 'Bachelor of Science in Nursing',               'code': 'BSN',   'duration': 4},
                {'name': 'Bachelor of Science in Medical Laboratory',    'code': 'BSML',  'duration': 4},
            ],
        },
        {
            'name': 'School of Business',
            'code': 'BUS',
            'description': 'Business, commerce and management.',
            'programmes': [
                {'name': 'Bachelor of Commerce',                    'code': 'BCOM',  'duration': 4},
                {'name': 'Bachelor of Business Administration',     'code': 'BBA',   'duration': 4},
                {'name': 'Bachelor of Science in Procurement',      'code': 'BSP',   'duration': 4},
            ],
        },
        {
            'name': 'School of Agriculture',
            'code': 'AGR',
            'description': 'Agriculture, food science and environment.',
            'programmes': [
                {'name': 'Bachelor of Science in Agriculture',          'code': 'BSA',  'duration': 4},
                {'name': 'Bachelor of Science in Food Science',         'code': 'BSFS', 'duration': 4},
                {'name': 'Bachelor of Science in Environmental Science','code': 'BSES', 'duration': 4},
            ],
        },
    ]

    for s in data:
        school = School(name=s['name'], code=s['code'], description=s['description'])
        db.session.add(school)
        db.session.flush()   # get school.id

        for p in s['programmes']:
            prog = Programme(
                name=p['name'], code=p['code'],
                duration=p['duration'], school_id=school.id
            )
            db.session.add(prog)

    db.session.commit()
    total_progs = sum(len(s['programmes']) for s in data)
    print(f"✅ Seeded {len(data)} schools and {total_progs} programmes.")


# ─────────────────────────────────────────────
# SEED — SAMPLE COURSES  (BIT only as example)
# ─────────────────────────────────────────────

def seed_sample_courses():
    """
    Seeds a starter set of BIT courses.
    Lecturers are assigned via the admin panel — lecturer_id left None here.
    Add more programmes' courses following the same pattern.
    """
    if Course.query.count() > 0:
        print("Courses already seeded."); return

    bit = Programme.query.filter_by(code='BIT').first()
    if not bit:
        print("❌ BIT programme not found. Run seed_schools_and_programmes() first.")
        return

    bbit = Programme.query.filter_by(code='BBIT').first()
    dit  = Programme.query.filter_by(code='DIT').first()

    courses = [
        # ── BIT Year 1 ──────────────────────────────────────────
        Course(code='ICS 1100', name='Introduction to Computing',       year=1, semester=1, programme_id=bit.id),
        Course(code='ICS 1101', name='Programming Fundamentals',        year=1, semester=1, programme_id=bit.id),
        Course(code='ICS 1102', name='Mathematics for Computing',       year=1, semester=1, programme_id=bit.id),
        Course(code='ICS 1200', name='Data Structures',                 year=1, semester=2, programme_id=bit.id),
        Course(code='ICS 1201', name='Computer Organisation',           year=1, semester=2, programme_id=bit.id),

        # ── BIT Year 2 ──────────────────────────────────────────
        Course(code='ICS 2100', name='Object Oriented Programming',     year=2, semester=1, programme_id=bit.id),
        Course(code='ICS 2101', name='Database Systems',                year=2, semester=1, programme_id=bit.id),
        Course(code='ICS 2102', name='Operating Systems',               year=2, semester=1, programme_id=bit.id),
        Course(code='ICS 2200', name='Electronics',                     year=2, semester=2, programme_id=bit.id),
        Course(code='ICS 2201', name='Computer Networks',               year=2, semester=2, programme_id=bit.id),

        # ── BIT Year 3 ──────────────────────────────────────────
        Course(code='ICS 3100', name='Software Engineering',            year=3, semester=1, programme_id=bit.id),
        Course(code='ICS 3101', name='Web Development',                 year=3, semester=1, programme_id=bit.id),
        Course(code='ICS 3200', name='Information Security',            year=3, semester=2, programme_id=bit.id),
        Course(code='ICS 3201', name='Mobile Application Development',  year=3, semester=2, programme_id=bit.id),

        # ── BIT Year 4 ──────────────────────────────────────────
        Course(code='ICS 4100', name='Research Methods',                year=4, semester=1, programme_id=bit.id),
        Course(code='ICS 4101', name='Artificial Intelligence',         year=4, semester=1, programme_id=bit.id),
        Course(code='ICS 4200', name='Final Year Project',              year=4, semester=2, programme_id=bit.id),

        # ── BBIT Year 1 ─────────────────────────────────────────
        Course(code='BBIT 1100', name='Introduction to Business IT',    year=1, semester=1, programme_id=bbit.id),
        Course(code='BBIT 1101', name='Business Mathematics',           year=1, semester=1, programme_id=bbit.id),
        Course(code='BBIT 1200', name='Principles of Management',       year=1, semester=2, programme_id=bbit.id),

        # ── DIT Year 1 ──────────────────────────────────────────
        Course(code='DIT 1100',  name='Computer Fundamentals',          year=1, semester=1, programme_id=dit.id),
        Course(code='DIT 1101',  name='Introduction to Programming',    year=1, semester=1, programme_id=dit.id),
    ]

    db.session.add_all(courses)
    db.session.commit()
    print(f"✅ Seeded {len(courses)} courses.")