import csv
import io
import atexit
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from ham import *
from face_attend import *

app = Flask(__name__)
app.secret_key = '06430313'  # Thay đổi key này bằng chuỗi ngẫu nhiên bảo mật

# ==========================================
# --- CONTEXT PROCESSOR (Dữ liệu toàn cục) ---
# ==========================================
@app.context_processor
def inject_notifications():
    """Tự động chèn biến 'notifications' vào tất cả template"""
    notifications = []
    unread_count = 0
    
    if 'loggedin' in session and 'ma_nv' in session:
        # [MỚI] Truyền thêm role_id để ham.py biết lấy thông báo cho ai
        role_id = session.get('role_id')
        notifications = lay_thong_bao_ca_nhan(session['ma_nv'], role_id)
        
        for n in notifications:
            if not n['DaDoc']:
                unread_count += 1
                
    return dict(notifications=notifications, unread_count=unread_count)

# --- API ĐÁNH DẤU ĐÃ ĐỌC ---
@app.route('/api/mark_notifications_read', methods=['POST'])
def api_mark_read():
    if 'loggedin' not in session: 
        return {"status": "error", "message": "Unauthorized"}
    
    ma_nv = session.get('ma_nv')
    role_id = session.get('role_id')
    
    # [MỚI] Truyền thêm role_id
    danh_dau_da_doc(ma_nv, role_id)
    return {"status": "success"}

# ==========================================
# --- SCHEDULER (Tác vụ tự động) ---
# ==========================================
def job_tinh_luong_tu_dong():
    """Tự động tính lương vào 00:00 ngày mùng 1 hàng tháng"""
    print(f"[{datetime.now()}] Đang chạy tác vụ tính lương tự động...")
    hom_nay = datetime.now()
    ngay_cuoi_thang_truoc = hom_nay.replace(day=1) - timedelta(days=1)
    thang_can_tinh = ngay_cuoi_thang_truoc.month
    nam_can_tinh = ngay_cuoi_thang_truoc.year
    
    try:
        success, msg = tinh_toan_va_luu_luong(thang_can_tinh, nam_can_tinh)
        if success:
            print(f"✅ Tự động tính lương thành công cho tháng {thang_can_tinh}/{nam_can_tinh}")
        else:
            print(f"❌ Lỗi tự động tính lương: {msg}")
    except Exception as e:
        print(f"❌ Exception trong scheduler: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=job_tinh_luong_tu_dong, trigger="cron", day='1', hour='0', minute='0')
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ==========================================
# --- HÀM BỔ TRỢ ---
# ==========================================
def get_week_navigation(current_date):
    """Tính ngày của tuần trước và tuần sau"""
    prev_week = (current_date - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (current_date + timedelta(days=7)).strftime('%Y-%m-%d')
    return prev_week, next_week

def get_month_navigation(month, year):
    """Tính tháng trước và tháng sau"""
    if month == 1: prev_m, prev_y = 12, year - 1
    else: prev_m, prev_y = month - 1, year
    
    if month == 12: next_m, next_y = 1, year + 1
    else: next_m, next_y = month + 1, year
    
    return (prev_m, prev_y), (next_m, next_y)

# ==========================================
# --- AUTHENTICATION & COMMON ---
# ==========================================

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/dangnhap', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = kiem_tra_dang_nhap(username, password)

        if user:
            session['loggedin'] = True
            session['username'] = user['tai_khoan']
            session['role_id'] = user['role_id']
            session['ma_nv'] = user['ma_nv']
            
            if user['role_id'] in ['QuanLyCapCao', 'QuanLyCapThap']: 
                return redirect(url_for('admin_trangchu'))
            else:
                return redirect(url_for('employee_trangchu'))
        else:
            flash('Sai tài khoản hoặc mật khẩu', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# --- EMPLOYEE ROUTES ---
# ==========================================

@app.route('/employee/TrangChu')
def employee_trangchu():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    cham_cong = lay_trang_thai_cham_cong_hom_nay(ma_nv)
    
    status_msg = ""
    status_color = "warning"
    if not cham_cong:
        status_msg = "Bạn chưa thực hiện chấm công hôm nay."
    elif cham_cong['CheckIn'] and not cham_cong['CheckOut']:
        gio_vao = cham_cong['CheckIn'].strftime('%H:%M')
        status_msg = f"Đã Check-in lúc {gio_vao}. Đang trong giờ làm việc."
        status_color = "info"
    elif cham_cong['CheckIn'] and cham_cong['CheckOut']:
        gio_ra = cham_cong['CheckOut'].strftime('%H:%M')
        status_msg = f"Hoàn thành công việc (Về lúc {gio_ra})."
        status_color = "success"

    return render_template('employee/trangchu.html', cham_cong=cham_cong, msg=status_msg, color=status_color)

@app.route('/employee/profile', methods=['GET', 'POST'])
def employee_profile():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')

    if request.method == 'POST':
        sdt = request.form.get('sdt')
        email = request.form.get('email')
        dia_chi = request.form.get('dia_chi')
        
        if cap_nhat_profile(ma_nv, sdt, email, dia_chi):
            flash('Cập nhật thông tin thành công!', 'success')
        else:
            flash('Có lỗi xảy ra khi cập nhật.', 'danger')
        return redirect(url_for('employee_profile'))

    info = lay_thong_tin_nhan_vien(ma_nv)
    return render_template('employee/profile.html', info=info)

@app.route('/employee/change_password', methods=['POST'])
def employee_change_password():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    mk_cu = request.form['mk_cu']
    mk_moi = request.form['mk_moi']
    xac_nhan_mk = request.form['xac_nhan_mk']
    
    if mk_moi != xac_nhan_mk:
        flash('Mật khẩu mới không khớp!', 'warning')
        return redirect(url_for('employee_profile'))
    
    success, msg = doi_mat_khau(ma_nv, mk_cu, mk_moi)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('employee_profile'))

@app.route('/employee/salary')
def employee_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    thang_loc = request.args.get('month')
    nam_loc = request.args.get('year')
    
    if thang_loc and nam_loc and thang_loc != 'all':
        bang_luong = lay_bang_luong(ma_nv, int(thang_loc), int(nam_loc))
    else:
        thang_loc = None
        nam_loc = None
        bang_luong = lay_bang_luong(ma_nv)
        
    nam_hien_tai = datetime.now().year
    
    return render_template('employee/salary.html', 
                           bang_luong=bang_luong, 
                           sel_thang=int(thang_loc) if thang_loc else None, 
                           sel_nam=int(nam_loc) if nam_loc else None, 
                           nam_hien_tai=nam_hien_tai)

@app.route('/employee/ung_luong', methods=['POST'])
def employee_ung_luong():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    so_tien = float(request.form['so_tien'])
    ly_do = request.form['ly_do']
    ngay_ung = request.form['ngay_ung']
    
    success, msg = gui_yeu_cau_ung_luong(ma_nv, so_tien, ly_do, ngay_ung)
    
    if success:
        flash(msg, 'success')
    else:
        flash(msg, 'danger')
        
    return redirect(url_for('employee_salary'))

@app.route('/employee/export_salary')
def export_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    export_type = request.args.get('type', 'all')
    
    if export_type == 'filter':
        try:
            thang = int(request.args.get('month'))
            nam = int(request.args.get('year'))
            data = lay_bang_luong(ma_nv, thang, nam)
            filename = f"Bang_Luong_T{thang}_{nam}.csv"
            msg_error = f"Không tìm thấy dữ liệu lương tháng {thang}/{nam}!"
        except (ValueError, TypeError):
            flash('Tham số không hợp lệ!', 'danger')
            return redirect(url_for('employee_salary'))
    else:
        data = lay_bang_luong(ma_nv)
        filename = "Lich_Su_Luong_Day_Du.csv"
        msg_error = "Chưa có lịch sử lương nào!"

    if not data:
        flash(msg_error, 'warning')
        return redirect(url_for('employee_salary'))

    si = io.StringIO()
    cw = csv.writer(si)
    si.write('\ufeff') 
    cw.writerow(['Kỳ Lương', 'Năm', 'Lương Cơ Bản', 'Thưởng', 'Phạt', 'Thực Lĩnh', 'Trạng Thái', 'Ngày Tạo'])
    
    for row in data:
        cw.writerow([
            f"Tháng {row['Thang']}", 
            row['Nam'], 
            "{:,.0f}".format(row['LuongCoBan']), 
            "{:,.0f}".format(row['ThuongThem']), 
            "{:,.0f}".format(row['Phat']), 
            "{:,.0f}".format(row['Tong']), 
            row['TrangThai'], 
            row['NgayTao']
        ])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return output

@app.route('/employee/attendlog')
def employee_attendlog():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    hien_tai = datetime.now()
    try:
        thang = int(request.args.get('month', hien_tai.month))
        nam = int(request.args.get('year', hien_tai.year))
    except ValueError:
        thang = hien_tai.month
        nam = hien_tai.year
        
    prev_m, next_m = get_month_navigation(thang, nam)
    attend_data = lay_du_lieu_cham_cong_thang(ma_nv, thang, nam)
    
    import calendar
    cal = calendar.monthcalendar(nam, thang)
    
    return render_template('employee/attendlog.html', 
                           calendar=cal, 
                           attend_data=attend_data, 
                           thang=thang, 
                           nam=nam,
                           prev_m=prev_m, 
                           next_m=next_m)

@app.route('/employee/schedule', methods=['GET', 'POST'])
def employee_schedule():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    if request.method == 'POST':
        loai_yc = request.form['loai_yc']
        ly_do = request.form['ly_do']
        ca_cu_info = request.form['ca_cu_chon'].split('|')
        ngay_cu = ca_cu_info[0]; ma_ca_cu = ca_cu_info[1]
        ngay_moi = request.form.get('ngay_moi') if loai_yc == 'DOI_CA' else None
        ma_ca_moi = request.form.get('ca_moi') if loai_yc == 'DOI_CA' else None
        
        if gui_yeu_cau_thay_doi(ma_nv, loai_yc, ly_do, ngay_cu, ma_ca_cu, ngay_moi, ma_ca_moi):
            flash('Đã gửi yêu cầu thành công!', 'success')
        else: 
            flash('Lỗi khi gửi yêu cầu.', 'danger')
        return redirect(url_for('employee_schedule'))

    date_str = request.args.get('date')
    if date_str:
        try: view_date = datetime.strptime(date_str, '%Y-%m-%d')
        except: view_date = datetime.now()
    else: view_date = datetime.now()
    
    real_today = datetime.now()
    prev_week, next_week = get_week_navigation(view_date)
    
    thu_hai = view_date - timedelta(days=view_date.weekday())
    danh_sach_ngay = []
    ten_thu = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    
    for i in range(7):
        ngay = thu_hai + timedelta(days=i)
        danh_sach_ngay.append({
            'date_obj': ngay, 
            'date_str': ngay.strftime('%Y-%m-%d'), 
            'display': ngay.strftime('%d/%m'), 
            'day_name': ten_thu[i]
        })
    
    cn = thu_hai + timedelta(days=6)
    du_lieu_lich = lay_lich_lam_viec(ma_nv, thu_hai.strftime('%Y-%m-%d'), cn.strftime('%Y-%m-%d'))
    ca_tuong_lai = lay_ca_tuong_lai_cua_nv(ma_nv)
    all_ca = lay_danh_sach_ca_lam()
    
    return render_template('employee/schedule.html', 
                           days=danh_sach_ngay, 
                           schedule=du_lieu_lich, 
                           hom_nay_str=real_today.strftime('%Y-%m-%d'), 
                           ca_tuong_lai=ca_tuong_lai, 
                           all_ca=all_ca, 
                           curr_date=view_date.strftime('%Y-%m-%d'), 
                           prev_week=prev_week, 
                           next_week=next_week)

# ==========================================
# --- ADMIN ROUTES ---
# ==========================================

@app.route('/admin/TrangChu')
def admin_trangchu():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']:
        return redirect(url_for('employee_trangchu'))
    
    stats = lay_thong_ke_dashboard()
    activities = lay_hoat_dong_gan_day()
    return render_template('admin/trangchu.html', stats=stats, activities=activities)

@app.route('/admin/personal_home')
def admin_personal_home():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('employee_trangchu'))
    
    ma_nv = session.get('ma_nv')
    cham_cong = lay_trang_thai_cham_cong_hom_nay(ma_nv)
    status_msg = ""; status_color = "warning"
    
    if not cham_cong:
        status_msg = "Bạn chưa thực hiện chấm công hôm nay."
    elif cham_cong['CheckIn'] and not cham_cong['CheckOut']:
        gio_vao = cham_cong['CheckIn'].strftime('%H:%M')
        status_msg = f"Đã Check-in lúc {gio_vao}. Đang trong giờ làm việc."
        status_color = "info"
    elif cham_cong['CheckIn'] and cham_cong['CheckOut']:
        gio_ra = cham_cong['CheckOut'].strftime('%H:%M')
        status_msg = f"Hoàn thành công việc (Về lúc {gio_ra})."
        status_color = "success"
        
    return render_template('admin/personal_home.html', cham_cong=cham_cong, msg=status_msg, color=status_color)

@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('employee_profile'))
    
    ma_nv = session.get('ma_nv')
    
    if request.method == 'POST':
        sdt = request.form.get('sdt')
        email = request.form.get('email')
        dia_chi = request.form.get('dia_chi')
        if cap_nhat_profile(ma_nv, sdt, email, dia_chi):
            flash('Cập nhật hồ sơ quản trị viên thành công!', 'success')
        else:
            flash('Có lỗi xảy ra.', 'danger')
        return redirect(url_for('admin_profile'))
        
    info = lay_thong_tin_nhan_vien(ma_nv)
    return render_template('admin/profile.html', info=info)

@app.route('/admin/change_password', methods=['POST'])
def admin_change_password():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    mk_cu = request.form['mk_cu']
    mk_moi = request.form['mk_moi']
    xac_nhan_mk = request.form['xac_nhan_mk']
    
    if mk_moi != xac_nhan_mk:
        flash('Mật khẩu mới không khớp!', 'warning')
        return redirect(url_for('admin_profile'))
        
    success, msg = doi_mat_khau(ma_nv, mk_cu, mk_moi)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('admin_profile'))

@app.route('/admin/salary')
def admin_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('employee_salary'))
    
    ma_nv = session.get('ma_nv')
    
    thang_loc = request.args.get('month')
    nam_loc = request.args.get('year')
    
    if thang_loc and nam_loc and thang_loc != 'all':
        bang_luong = lay_bang_luong(ma_nv, int(thang_loc), int(nam_loc))
    else:
        thang_loc = None
        nam_loc = None
        bang_luong = lay_bang_luong(ma_nv)
        
    nam_hien_tai = datetime.now().year
    
    return render_template('admin/salary.html', 
                           bang_luong=bang_luong, 
                           sel_thang=int(thang_loc) if thang_loc else None, 
                           sel_nam=int(nam_loc) if nam_loc else None, 
                           nam_hien_tai=nam_hien_tai)

@app.route('/admin/export_salary')
def admin_export_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    export_type = request.args.get('type', 'all')
    
    if export_type == 'filter':
        try:
            thang = int(request.args.get('month'))
            nam = int(request.args.get('year'))
            data = lay_bang_luong(ma_nv, thang, nam)
            filename = f"Bang_Luong_Admin_T{thang}_{nam}.csv"
        except:
            data = lay_bang_luong(ma_nv)
            filename = "Lich_Su_Luong_Admin.csv"
    else:
        data = lay_bang_luong(ma_nv)
        filename = "Lich_Su_Luong_Admin.csv"
        
    if not data:
        flash("Không có dữ liệu lương để xuất!", 'warning')
        return redirect(url_for('admin_salary'))
        
    si = io.StringIO()
    cw = csv.writer(si)
    si.write('\ufeff') 
    cw.writerow(['Kỳ Lương', 'Năm', 'Lương Cơ Bản', 'Thưởng', 'Phạt', 'Thực Lĩnh', 'Trạng Thái', 'Ngày Tạo'])
    
    for row in data:
        cw.writerow([
            f"Tháng {row['Thang']}", 
            row['Nam'], 
            "{:,.0f}".format(row['LuongCoBan']), 
            "{:,.0f}".format(row['ThuongThem']), 
            "{:,.0f}".format(row['Phat']), 
            "{:,.0f}".format(row['Tong']), 
            row['TrangThai'], 
            row['NgayTao']
        ])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return output

@app.route('/admin/attendlog')
def admin_attendlog():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    hien_tai = datetime.now()
    try:
        thang = int(request.args.get('month', hien_tai.month))
        nam = int(request.args.get('year', hien_tai.year))
    except ValueError:
        thang = hien_tai.month
        nam = hien_tai.year
        
    prev_m, next_m = get_month_navigation(thang, nam)
    attend_data = lay_du_lieu_cham_cong_thang(ma_nv, thang, nam)
    
    import calendar
    cal = calendar.monthcalendar(nam, thang)
    
    return render_template('admin/attendlog.html', 
                           calendar=cal, 
                           attend_data=attend_data, 
                           thang=thang, 
                           nam=nam,
                           prev_m=prev_m, 
                           next_m=next_m)

@app.route('/admin/schedule', methods=['GET', 'POST'])
def admin_schedule():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: return redirect(url_for('employee_schedule'))
    ma_nv = session.get('ma_nv')
    
    if request.method == 'POST':
        loai_yc = request.form['loai_yc']
        ly_do = request.form['ly_do']
        ca_cu_info = request.form['ca_cu_chon'].split('|')
        ngay_cu = ca_cu_info[0]; ma_ca_cu = ca_cu_info[1]
        ngay_moi = request.form.get('ngay_moi') if loai_yc == 'DOI_CA' else None
        ma_ca_moi = request.form.get('ca_moi') if loai_yc == 'DOI_CA' else None
        
        if gui_yeu_cau_thay_doi(ma_nv, loai_yc, ly_do, ngay_cu, ma_ca_cu, ngay_moi, ma_ca_moi):
            flash('Đã gửi yêu cầu thành công!', 'success')
        else: 
            flash('Lỗi khi gửi yêu cầu.', 'danger')
        return redirect(url_for('admin_schedule'))

    date_str = request.args.get('date')
    if date_str:
        try: view_date = datetime.strptime(date_str, '%Y-%m-%d')
        except: view_date = datetime.now()
    else: view_date = datetime.now()
    
    real_today = datetime.now()
    prev_week, next_week = get_week_navigation(view_date)
    
    thu_hai = view_date - timedelta(days=view_date.weekday())
    danh_sach_ngay = []
    ten_thu = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    
    for i in range(7):
        ngay = thu_hai + timedelta(days=i)
        danh_sach_ngay.append({'date_obj': ngay, 'date_str': ngay.strftime('%Y-%m-%d'), 'display': ngay.strftime('%d/%m'), 'day_name': ten_thu[i]})
    
    cn = thu_hai + timedelta(days=6)
    du_lieu_lich = lay_lich_lam_viec(ma_nv, thu_hai.strftime('%Y-%m-%d'), cn.strftime('%Y-%m-%d'))
    ca_tuong_lai = lay_ca_tuong_lai_cua_nv(ma_nv)
    all_ca = lay_danh_sach_ca_lam()
    
    return render_template('admin/schedule.html', 
                           days=danh_sach_ngay, 
                           schedule=du_lieu_lich, 
                           hom_nay_str=real_today.strftime('%Y-%m-%d'), 
                           ca_tuong_lai=ca_tuong_lai, 
                           all_ca=all_ca, 
                           curr_date=view_date.strftime('%Y-%m-%d'), 
                           prev_week=prev_week, 
                           next_week=next_week)

# ==========================================
# --- ADMIN FEATURES ROUTES ---
# ==========================================

@app.route('/admin/nhan_su')
def admin_nhan_su():
    if 'loggedin' not in session or session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('login'))
    
    keyword = request.args.get('keyword', '').strip()
    filters = request.args.getlist('filters') 
    
    ds_nv = lay_danh_sach_nhan_vien(keyword, filters)
    ds_pb = lay_danh_sach_phong_ban()
    
    return render_template('admin/qlNhanSu.html', 
                           ds_nv=ds_nv, 
                           ds_pb=ds_pb, 
                           curr_keyword=keyword, 
                           curr_filters=filters)

@app.route('/admin/nhan_su/them', methods=['POST'])
def admin_them_nv():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    ho_ten = request.form['ho_ten']
    sdt = request.form['sdt']
    email = request.form['email']
    chuc_vu = request.form['chuc_vu']
    luong = request.form['luong']
    phong_ban = request.form['phong_ban']
    tai_khoan = request.form['tai_khoan']
    mat_khau = request.form['mat_khau']
    
    if them_nhan_vien_moi(ho_ten, sdt, email, chuc_vu, luong, phong_ban, tai_khoan, mat_khau):
        flash('Thêm nhân viên và tài khoản thành công!', 'success')
    else:
        flash('Lỗi! Có thể tên tài khoản đã tồn tại.', 'danger')
        
    return redirect(url_for('admin_nhan_su'))

@app.route('/admin/nhan_su/sua', methods=['POST'])
def admin_sua_nv():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    ma_nv = request.form['ma_nv']
    ho_ten = request.form['ho_ten']
    sdt = request.form['sdt']
    email = request.form['email']
    chuc_vu = request.form['chuc_vu']
    luong = request.form['luong']
    phong_ban = request.form['phong_ban']
    tai_khoan = request.form['tai_khoan']
    mat_khau = request.form['mat_khau']
    
    if cap_nhat_nhan_vien_admin(ma_nv, ho_ten, sdt, email, chuc_vu, luong, phong_ban, tai_khoan, mat_khau):
        flash('Cập nhật thông tin và tài khoản thành công!', 'success')
    else:
        flash('Lỗi cập nhật!', 'danger')
        
    return redirect(url_for('admin_nhan_su'))

@app.route('/admin/nhan_su/xoa/<int:ma_nv>')
def admin_xoa_nv(ma_nv):
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    if ma_nv == session.get('ma_nv'):
        flash('Bạn không thể tự xóa tài khoản của mình!', 'warning')
        return redirect(url_for('admin_nhan_su'))
        
    if xoa_nhan_vien(ma_nv):
        flash('Đã xóa nhân viên khỏi hệ thống!', 'success')
    else:
        flash('Lỗi khi xóa nhân viên!', 'danger')
        
    return redirect(url_for('admin_nhan_su'))

@app.route('/admin/cham_cong')
def admin_ql_cham_cong():
    if 'loggedin' not in session or session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('login'))
    
    ngay_chon = request.args.get('date')
    tu_khoa = request.args.get('keyword', '').strip()
    
    if not ngay_chon:
        ngay_chon = datetime.now().strftime('%Y-%m-%d')
        
    ds_cong = lay_bang_cham_cong_ngay(ngay_chon, tu_khoa)
    ds_log = lay_lich_su_chinh_sua('AttendLog')
    
    return render_template('admin/qlChamCong.html', 
                           ds_cong=ds_cong, 
                           ngay_chon=ngay_chon, 
                           curr_keyword=tu_khoa, 
                           ds_log=ds_log)

@app.route('/admin/cham_cong/sua', methods=['POST'])
def admin_sua_cc():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    log_id = request.form['log_id']
    gio_vao = request.form['gio_vao']
    gio_ra = request.form['gio_ra']
    ngay_chon = request.form['ngay_chon']
    admin_id = session.get('ma_nv') 
    
    if admin_sua_cham_cong(log_id, gio_vao, gio_ra, ngay_chon, admin_id):
        flash('Đã cập nhật và ghi lại lịch sử thay đổi!', 'success')
    else:
        flash('Lỗi cập nhật!', 'danger')
        
    return redirect(url_for('admin_ql_cham_cong', date=ngay_chon))

@app.route('/admin/quan_ly_luong')
def admin_ql_luong():
    if 'loggedin' not in session or session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('login'))
    
    hien_tai = datetime.now()
    try:
        thang = int(request.args.get('month', hien_tai.month))
        nam = int(request.args.get('year', hien_tai.year))
    except:
        thang = hien_tai.month
        nam = hien_tai.year
        
    keyword = request.args.get('keyword', '').strip()
    role_filter = request.args.get('role', 'all')
    
    ds_luong = lay_ds_bang_luong_admin(thang, nam, keyword, role_filter)
    ds_log = lay_lich_su_chinh_sua('Salary')
    ds_yeu_cau_ung = lay_ds_yeu_cau_ung_luong()
    
    return render_template('admin/qlLuong.html', 
                           ds_luong=ds_luong, 
                           ds_log=ds_log, 
                           ds_yeu_cau_ung=ds_yeu_cau_ung, 
                           thang=thang, nam=nam, 
                           hien_tai=hien_tai, 
                           curr_keyword=keyword, 
                           curr_role=role_filter)

@app.route('/admin/tinh_luong', methods=['POST'])
def admin_tinh_luong_action():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    thang = int(request.form['thang'])
    nam = int(request.form['nam'])
    
    success, msg = tinh_toan_va_luu_luong(thang, nam)
    
    if success:
        flash(msg, 'success')
    else:
        flash(f'Lỗi tính lương: {msg}', 'danger')
        
    return redirect(url_for('admin_ql_luong', month=thang, year=nam))

@app.route('/admin/cap_nhat_thuong_phat', methods=['POST'])
def admin_update_thuong_phat():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    salary_id = request.form['salary_id']
    thuong = request.form['thuong']
    phat = request.form['phat']
    ung_luong = request.form['ung_luong']
    thang_ht = request.form['thang_hien_tai'] 
    nam_ht = request.form['nam_hien_tai']
    admin_id = session.get('ma_nv')
    
    if cap_nhat_thuong_phat(salary_id, thuong, phat, ung_luong, admin_id):
        flash('Đã cập nhật các khoản điều chỉnh!', 'success')
    else:
        flash('Lỗi cập nhật!', 'danger')
        
    return redirect(url_for('admin_ql_luong', month=thang_ht, year=nam_ht))

@app.route('/admin/duyet_luong/<int:salary_id>')
def admin_duyet_luong_action(salary_id):
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    thang = request.args.get('month')
    nam = request.args.get('year')
    
    if duyet_thanh_toan_luong(salary_id):
        flash('Đã duyệt thanh toán lương thành công!', 'success')
    else:
        flash('Lỗi khi duyệt lương!', 'danger')
        
    return redirect(url_for('admin_ql_luong', month=thang, year=nam))

@app.route('/admin/duyet_tat_ca', methods=['POST'])
def admin_duyet_tat_ca_action():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    thang = request.form['thang']
    nam = request.form['nam']
    keyword = request.form.get('keyword', '').strip()
    role = request.form.get('role', 'all')
    
    if duyet_tat_ca_luong_thang(thang, nam, keyword, role):
        msg = 'Đã duyệt các bản ghi phù hợp với bộ lọc!' if keyword or role != 'all' else f'Đã duyệt toàn bộ lương tháng {thang}/{nam}!'
        flash(msg, 'success')
    else:
        flash('Lỗi khi duyệt hàng loạt!', 'danger')
        
    return redirect(url_for('admin_ql_luong', month=thang, year=nam, keyword=keyword, role=role))

@app.route('/admin/duyet_ung_luong', methods=['POST'])
def admin_duyet_ung_luong_action():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    ma_yc = request.form['ma_yc']
    trang_thai = request.form['trang_thai']
    admin_id = session.get('ma_nv')
    
    if duyet_ung_luong(ma_yc, trang_thai, admin_id):
        flash(f'Đã {trang_thai} yêu cầu ứng lương!', 'success')
    else:
        flash('Lỗi xử lý yêu cầu.', 'danger')
        
    return redirect(url_for('admin_ql_luong'))

@app.route('/admin/face_register')
def admin_face_register():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ds_nv = lay_danh_sach_nhan_vien()
    return render_template('admin/face_register.html', ds_nv=ds_nv)

@app.route('/api/face/register', methods=['POST'])
def api_face_register():
    data = request.json
    ma_nv = data.get('ma_nv')
    image = data.get('image')
    
    if not ma_nv or not image:
        return {"status": "error", "message": "Thiếu dữ liệu"}
        
    ok, msg = luu_khuon_mat_db(ma_nv, image)
    if ok:
        return {"status": "success", "message": msg}
    return {"status": "error", "message": msg}

@app.route('/api/face/attend', methods=['POST'])
def api_face_attend():
    data = request.json
    image = data.get('image')
    
    if not image:
        return {"status": "error", "message": "Thiếu ảnh"}
        
    result = cham_cong_bang_khuon_mat(image)
    return result

@app.route('/cham_cong_face_id')
def trang_cham_cong_face():
    return render_template('chamcong.html')

@app.route('/admin/quan_ly_ca', methods=['GET', 'POST'])
def admin_ql_ca():
    if 'loggedin' not in session or session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        if 'action' in request.form and request.form['action'] == 'auto_schedule':
            start = request.form['tuan_start']
            end = request.form['tuan_end']
            if xep_ca_tu_dong(start, end):
                flash('Đã xếp ca tự động thành công!', 'success')
            else:
                flash('Lỗi xếp ca.', 'danger')
            return redirect(url_for('admin_ql_ca'))
            
        if 'action' in request.form and request.form['action'] == 'approve_request':
            ma_yc = request.form['ma_yc']
            trang_thai = request.form['trang_thai']
            if duyet_yeu_cau(ma_yc, trang_thai):
                flash(f'Đã {trang_thai} yêu cầu!', 'success')
            else:
                flash('Lỗi xử lý yêu cầu.', 'danger')
            return redirect(url_for('admin_ql_ca'))
            
    ds_yeu_cau = lay_danh_sach_yeu_cau()
    return render_template('admin/qlCa.html', ds_yeu_cau=ds_yeu_cau)


if __name__ == '__main__':
    app.run(debug=True)
