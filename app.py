from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from flask_migrate import Migrate

from models import db, User, School, Programme, Course, Room, Lecture, Enrollment, Notification
from scheduler import (get_available_rooms, check_lecturer_conflict,
                       notify_enrolled_students,
                       seed_rooms, seed_schools_and_programmes, seed_sample_courses)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



# LANDING
@app.route('/')
def landing():
    return render_template('landing.html')



# AUTH — REGISTER
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name',  '').strip()
        email      = request.form.get('email',      '').strip()
        password   = request.form.get('password',   '')

        if not all([first_name, last_name, email, password]):
            flash('All fields are required.', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('That email is already registered.', 'error')
            return render_template('register.html')

        if email.endswith('@students.jkuat.ac.ke'):
            role = 'student'
        elif email.endswith('@jkuat.ac.ke'):
            role = 'lecturer'
        else:
            flash('Use a valid JKUAT email address.', 'error')
            return render_template('register.html')

        user = User(
            name     = f'{first_name} {last_name}'.strip(),
            email    = email,
            password = generate_password_hash(password),
            role     = role,
        )
        db.session.add(user)
        db.session.commit()

        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')



# AUTH — LOGIN / LOGOUT
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user.role == 'lecturer':
            return redirect(url_for('lecturer_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            if current_user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif current_user.role == 'lecturer':
                return redirect(url_for('lecturer_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))



# STUDENT DASHBOARD
@app.route('/student')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        return redirect(url_for('lecturer_dashboard'))

    # Only lectures for courses the student is enrolled in
    enrolled_ids = [e.course_id for e in current_user.enrollments]

    lectures = Lecture.query\
        .filter(Lecture.course_id.in_(enrolled_ids))\
        .order_by(Lecture.day, Lecture.start_time)\
        .all() if enrolled_ids else []

    notifications = Notification.query\
        .filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc())\
        .limit(20).all()

    unread = current_user.unread_count()

    return render_template('student_dashboard.html',
                           user=current_user,
                           lectures=lectures,
                           notifications=notifications,
                           unread=unread)


# NOTIFICATIONS — mark as read (AJAX)
@app.route('/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query\
        .filter_by(user_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True})



# STUDENT PROFILE — self-enroll in courses
@app.route('/profile')
@login_required
def profile():
    if current_user.role != 'student':
        return redirect(url_for('lecturer_dashboard'))

    schools     = School.query.order_by(School.name).all()
    enrolled    = {e.course_id for e in current_user.enrollments}
    enrollments = Enrollment.query.filter_by(student_id=current_user.id)\
                            .order_by(Enrollment.enrolled_at.desc()).all()

    return render_template('student_profile.html',
                           user=current_user,
                           schools=schools,
                           enrolled=enrolled,
                           enrollments=enrollments)


@app.route('/enroll/<int:course_id>', methods=['POST'])
@login_required
def enroll(course_id):
    if current_user.role != 'student':
        return jsonify({'error': 'Only students can enroll.'}), 403

    course = Course.query.get_or_404(course_id)

    try:
        e = Enrollment(student_id=current_user.id, course_id=course_id)
        db.session.add(e)
        db.session.commit()
        return jsonify({'ok': True, 'message': f'Enrolled in {course.code} — {course.name}'})
    except IntegrityError:
        db.session.rollback()
        return jsonify({'ok': False, 'message': 'Already enrolled in this course.'})


@app.route('/unenroll/<int:course_id>', methods=['POST'])
@login_required
def unenroll(course_id):
    if current_user.role != 'student':
        return jsonify({'error': 'Forbidden'}), 403

    e = Enrollment.query.filter_by(
        student_id=current_user.id, course_id=course_id
    ).first_or_404()

    db.session.delete(e)
    db.session.commit()
    return jsonify({'ok': True, 'message': 'Unenrolled successfully.'})



# API — courses by programme (for profile filter)
@app.route('/api/courses/<int:programme_id>')
@login_required
def api_courses(programme_id):
    courses = Course.query.filter_by(programme_id=programme_id)\
                          .order_by(Course.year, Course.semester, Course.code).all()
    return jsonify([{
        'id':       c.id,
        'code':     c.code,
        'name':     c.name,
        'year':     c.year,
        'semester': c.semester,
        'enrolled': any(e.course_id == c.id for e in current_user.enrollments),
    } for c in courses])



# LECTURER DASHBOARD
@app.route('/lecturer')
@login_required
def lecturer_dashboard():
    if current_user.role != 'lecturer':
        return redirect(url_for('student_dashboard'))

    lectures = Lecture.query\
        .filter_by(lecturer_id=current_user.id)\
        .order_by(Lecture.day, Lecture.start_time)\
        .all()

    # Only courses assigned to this lecturer
    courses = Course.query.filter_by(lecturer_id=current_user.id)\
                          .order_by(Course.programme_id, Course.year, Course.code).all()

    return render_template('lecturer_dashboard.html',
                           user=current_user,
                           lectures=lectures,
                           courses=courses)



# ROOMS available (AJAX)
@app.route('/rooms/available', methods=['POST'])
@login_required
def available_rooms():
    day       = request.form.get('day',        '').strip()
    start_str = request.form.get('start_time', '').strip()
    end_str   = request.form.get('end_time',   '').strip()

    if not all([day, start_str, end_str]):
        return jsonify({'error': 'Missing fields.'}), 400

    try:
        start = datetime.strptime(start_str, '%H:%M').time()
        end   = datetime.strptime(end_str,   '%H:%M').time()
    except ValueError:
        return jsonify({'error': 'Invalid time format.'}), 400

    if start >= end:
        return jsonify({'error': 'Start must be before end.'}), 400

    rooms = get_available_rooms(day, start, end)
    return jsonify({'rooms': [r.to_dict() for r in rooms]})



# CREATE LECTURE
@app.route('/create-lecture', methods=['POST'])
@login_required
def create_lecture():
    if current_user.role != 'lecturer':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))

    course_id = request.form.get('course_id', '').strip()
    room_id   = request.form.get('room_id',   '').strip()
    day       = request.form.get('day',       '').strip()
    start_str = request.form.get('start_time','').strip()
    end_str   = request.form.get('end_time',  '').strip()

    if not all([course_id, room_id, day, start_str, end_str]):
        flash('All fields are required.', 'error')
        return redirect(url_for('lecturer_dashboard'))

    try:
        start      = datetime.strptime(start_str, '%H:%M').time()
        end        = datetime.strptime(end_str,   '%H:%M').time()
        course_id  = int(course_id)
        room_id    = int(room_id)
    except ValueError:
        flash('Invalid data submitted.', 'error')
        return redirect(url_for('lecturer_dashboard'))

    if start >= end:
        flash('Start time must be before end time.', 'error')
        return redirect(url_for('lecturer_dashboard'))

    # Guard 1 verify lecturer owns this course
    course = Course.query.get_or_404(course_id)
    if course.lecturer_id != current_user.id:
        flash('You are not assigned to that course.', 'error')
        return redirect(url_for('lecturer_dashboard'))

    # Guard 2 lecturer personal conflict
    if check_lecturer_conflict(current_user.id, day, start, end):
        flash('You already have a lecture during this time slot.', 'error')
        return redirect(url_for('lecturer_dashboard'))

    # Guard 3 room still free? (race condition)
    free_ids = {r.id for r in get_available_rooms(day, start, end)}
    if room_id not in free_ids:
        flash('That room was just taken. Please select another.', 'error')
        return redirect(url_for('lecturer_dashboard'))

    # Save lecture
    lecture = Lecture(
        course_id   = course_id,
        room_id     = room_id,
        day         = day,
        start_time  = start,
        end_time    = end,
        lecturer_id = current_user.id,
    )
    db.session.add(lecture)
    db.session.flush()   # gives lecture.id for notifications

    # ── Step 6: Dispatch targeted notifications ──
    notified = notify_enrolled_students(lecture)

    db.session.commit()

    room = Room.query.get(room_id)
    flash(
        f'"{course.name}" scheduled in {room.name} — {day} {start_str}–{end_str}. '
        f'{notified} student(s) notified.',
        'success'
    )
    return redirect(url_for('lecturer_dashboard'))



# DELETE LECTURE
@app.route('/delete-lecture/<int:lecture_id>', methods=['POST'])
@login_required
def delete_lecture(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)

    if lecture.lecturer_id != current_user.id:
        flash('You can only delete your own lectures.', 'error')
        return redirect(url_for('lecturer_dashboard'))

    # Clean up linked notifications
    Notification.query.filter_by(lecture_id=lecture_id).delete()

    db.session.delete(lecture)
    db.session.commit()
    flash('Lecture deleted.', 'success')
    return redirect(url_for('lecturer_dashboard'))



# ADMIN SEED
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))

    # Core data
    rooms = Room.query.all()
    schools = School.query.all()
    programmes = Programme.query.all()
    courses = Course.query.all()

    lecturers = User.query.filter_by(role='lecturer').all()
    students = User.query.filter_by(role='student').all()

    # Stats
    total_lectures = Lecture.query.count()
    assigned_courses = Course.query.filter(Course.lecturer_id.isnot(None)).count()
    unassigned_courses = Course.query.filter_by(lecturer_id=None).count()

    # Recent lectures
    recent_lectures = Lecture.query.order_by(Lecture.id.desc()).limit(10).all()

    return render_template(
        "admin_dashboard.html",
        rooms=rooms,
        schools=schools,
        programmes=programmes,
        courses=courses,
        lecturers=lecturers,
        students=students,
        total_lectures=total_lectures,
        assigned_courses=assigned_courses,
        unassigned_courses=unassigned_courses,
        recent_lectures=recent_lectures
    )


@app.route('/admin/seed-rooms')
@login_required
def admin_seed_rooms():
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))
    seed_rooms()
    flash('Rooms seeded successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/seed-schools')
@login_required
def admin_seed_schools():
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))
    seed_schools_and_programmes()
    flash('Schools and programmes seeded.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/seed-courses')
@login_required
def admin_seed_courses():
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))
    seed_sample_courses()
    flash('Sample courses seeded.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/assign-lecturer', methods=['GET', 'POST'])
@login_required
def admin_assign_lecturer():
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        course_id   = int(request.form.get('course_id'))
        lecturer_id = int(request.form.get('lecturer_id'))
        course   = Course.query.get_or_404(course_id)
        lecturer = User.query.get_or_404(lecturer_id)
        if lecturer.role != 'lecturer':
            flash('Selected user is not a lecturer.', 'error')
        else:
            course.lecturer_id = lecturer_id
            db.session.commit()
            flash(f'{lecturer.name} assigned to {course.code} — {course.name}.', 'success')
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)