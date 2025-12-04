import csv
import io
import atexit
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, send_file
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from ham import *
from face_attend import *
import pandas as pd
from io import BytesIO
import openpyxl

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

#--- SALARY ---#

@app.route('/employee/salary')
def employee_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    # Lấy tham số lọc
    hien_tai = datetime.now()
    req_month = request.args.get('month', 'all') # Mặc định là 'all' hoặc tháng hiện tại tùy bạn
    thang = int(req_month) if req_month != 'all' else 'all'
    
    req_year = request.args.get('year', str(hien_tai.year))
    nam = int(req_year) if req_year != 'all' else 'all'
    
    # Lấy dữ liệu bảng lương
    bang_luong = lay_bang_luong(ma_nv, thang, nam)
    
    # Tính hạn mức ứng lương (cho Modal)
    # Lưu ý: Hạn mức luôn tính theo thời điểm hiện tại thực tế để ứng tiền
    luong_cb, da_ung, con_lai = lay_han_muc_ung_luong(ma_nv, hien_tai.month, hien_tai.year)
    limit_info = {'luong_cb': luong_cb, 'da_ung': da_ung, 'max_50': luong_cb*0.5, 'con_lai': con_lai}

    return render_template('employee/salary.html', 
                           bang_luong=bang_luong, 
                           limit_info=limit_info,
                           sel_thang=thang, 
                           sel_nam=nam, 
                           hien_tai=hien_tai)

@app.route('/employee/ung_luong', methods=['POST'])
def employee_ung_luong_action():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    try:
        # Lấy số tiền (float để chấp nhận số lẻ, nhưng thường tiền Việt là int)
        so_tien = float(request.form['so_tien'])
        ly_do = request.form['ly_do']
        ngay_ung_str = request.form['ngay_ung']
        
        # Lấy tháng năm từ ngày chọn
        ngay_ung_date = datetime.strptime(ngay_ung_str, '%Y-%m-%d')
        thang_ung = ngay_ung_date.month
        nam_ung = ngay_ung_date.year

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. CHẶN NẾU THÁNG ĐÓ ĐÃ THANH TOÁN
        cursor.execute("SELECT TrangThai FROM Salary WHERE MaNV = ? AND Thang = ? AND Nam = ?", (ma_nv, thang_ung, nam_ung))
        row_salary = cursor.fetchone()
        if row_salary and row_salary.TrangThai == 'Đã thanh toán':
            flash(f'Tháng {thang_ung}/{nam_ung} đã chốt lương, không thể ứng thêm!', 'danger')
            return redirect(url_for('employee_salary'))

        # 2. TÍNH HẠN MỨC (50% Lương - Đã ứng)
        hien_tai = datetime.now()
        cursor.execute("SELECT LuongCoBan FROM Employee WHERE MaNV = ?", (ma_nv,))
        row_nv = cursor.fetchone()
        luong_cb = float(row_nv.LuongCoBan) if row_nv and row_nv.LuongCoBan else 0
        
        # Lấy tổng tiền đã ứng trong tháng hiện tại (bao gồm cả chờ duyệt)
        cursor.execute("""
            SELECT SUM(SoTien) FROM YeuCau 
            WHERE MaNV = ? AND LoaiYeuCau = 'UNG_LUONG' 
            AND TrangThai IN (N'DaDuyet', N'ChoDuyet') 
            AND MONTH(NgayTao) = ? AND YEAR(NgayTao) = ?
        """, (ma_nv, hien_tai.month, hien_tai.year))
        
        da_ung = float(cursor.fetchone()[0] or 0)
        
        max_duoc_ung = luong_cb * 0.5
        con_lai = max_duoc_ung - da_ung
        
        # 3. KIỂM TRA ĐIỀU KIỆN
        if so_tien < 100000:
            flash('Số tiền ứng phải lớn hơn hoặc bằng 100,000đ!', 'danger')
        
        elif so_tien > con_lai:
            # Format tiền đẹp mắt (VD: 1,234,567đ)
            msg = f"Số tiền vượt quá hạn mức! Bạn chỉ còn được ứng tối đa {int(con_lai):,}đ"
            flash(msg, 'danger')
            
        else:
            # 4. HỢP LỆ -> LƯU VÀO DB
            cursor.execute("""
                INSERT INTO YeuCau (MaNV, LoaiYeuCau, SoTien, LyDo, TrangThai, NgayTao, NgayCanNghi)
                VALUES (?, 'UNG_LUONG', ?, ?, N'ChoDuyet', GETDATE(), ?)
            """, (ma_nv, so_tien, ly_do, ngay_ung_str))
            
            conn.commit()
            flash(f'Đã gửi yêu cầu ứng {int(so_tien):,}đ thành công!', 'success')
            
    except ValueError:
        flash('Lỗi dữ liệu nhập vào!', 'danger')
    except Exception as e:
        flash(f'Lỗi hệ thống: {str(e)}', 'danger')
    finally:
        if 'conn' in locals(): conn.close()
        
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

@app.route('/employee/gui_yeu_cau_ung', methods=['POST'])
def employee_gui_yeu_cau_ung():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    ma_nv = session.get('ma_nv')
    so_tien_muon_ung = float(request.form.get('so_tien', 0))
    ly_do = request.form.get('ly_do', '')
    
    # --- BẮT ĐẦU KIỂM TRA ĐIỀU KIỆN ---
    luong_cb, da_ung, max_limit, con_lai = lay_han_muc_ung_luong(ma_nv)
    
    # Điều kiện 1: Tối thiểu 100k
    if so_tien_muon_ung < 100000:
        flash('Số tiền ứng phải tối thiểu 100,000đ!', 'danger')
        return redirect(url_for('employee_salary')) # Hoặc trang tương ứng
        
    # Điều kiện 2: Không vượt quá 50% (tính cả tiền cũ)
    # Tức là số tiền muốn ứng không được lớn hơn số dư hạn mức còn lại
    if so_tien_muon_ung > con_lai:
        msg = f"Bạn chỉ còn được ứng tối đa {int(con_lai):,}đ (Tổng hạn mức 50%: {int(max_limit):,}đ, Đã dùng: {int(da_ung):,}đ)"
        flash(msg, 'danger')
        return redirect(url_for('employee_salary'))

    # --- NẾU THỎA MÃN THÌ LƯU VÀO DB ---
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO YeuCau (MaNV, LoaiYeuCau, SoTien, LyDo, TrangThai, NgayTao)
            VALUES (?, 'UNG_LUONG', ?, ?, N'ChoDuyet', GETDATE())
        """, (ma_nv, so_tien_muon_ung, ly_do))
        conn.commit()
        flash('Gửi yêu cầu ứng lương thành công!', 'success')
    except Exception as e:
        flash(f'Lỗi hệ thống: {e}', 'danger')
    finally:
        conn.close()
        
    return redirect(url_for('employee_salary'))



#--- ATETENDLOG ---#
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
    calendar.setfirstweekday(calendar.SUNDAY) 
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
            flash('Cập nhật thông tin thành công!', 'success')
        else:
            flash('Có lỗi xảy ra khi cập nhật.', 'danger')
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


# --- 2. LỊCH SỬ CHẤM CÔNG (ADMIN) ---
@app.route('/admin/attendlog')
def admin_attendlog():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('employee_attendlog'))
        
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
    calendar.setfirstweekday(calendar.SUNDAY)
    cal = calendar.monthcalendar(nam, thang)
    
    return render_template('admin/attendlog.html', 
                           calendar=cal, 
                           attend_data=attend_data, 
                           thang=thang, 
                           nam=nam,
                           prev_m=prev_m, 
                           next_m=next_m)


# --- 3. LỊCH LÀM VIỆC & ĐỔI CA (ADMIN) ---
@app.route('/admin/schedule', methods=['GET', 'POST'])
def admin_schedule():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('employee_schedule'))
        
    ma_nv = session.get('ma_nv')
    
    # Xử lý gửi yêu cầu đổi ca (Dùng chung logic với nhân viên)
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

    # Hiển thị lịch
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
    
    return render_template('admin/schedule.html', 
                           days=danh_sach_ngay, 
                           schedule=du_lieu_lich, 
                           hom_nay_str=real_today.strftime('%Y-%m-%d'), 
                           ca_tuong_lai=ca_tuong_lai, 
                           all_ca=all_ca, 
                           curr_date=view_date.strftime('%Y-%m-%d'), 
                           prev_week=prev_week, 
                           next_week=next_week)

# --- 4. BẢNG LƯƠNG CÁ NHÂN (ADMIN) ---
@app.route('/admin/salary')
def admin_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('employee_salary'))
        
    ma_nv = session.get('ma_nv')
    hien_tai = datetime.now()
    
    # 1. Lấy filter từ URL
    req_month = request.args.get('month', 'all')
    thang = int(req_month) if req_month != 'all' else 'all'
    
    req_year = request.args.get('year', str(hien_tai.year))
    nam = int(req_year) if req_year != 'all' else 'all'
    
    # 2. Lấy dữ liệu bảng lương (Sử dụng hàm chung lay_bang_luong)
    bang_luong = lay_bang_luong(ma_nv, thang, nam)
    
    # 3. Tính hạn mức ứng lương (cho Modal Ứng Lương)
    # Lưu ý: Luôn tính theo thời điểm hiện tại thực tế để ứng tiền
    luong_cb, da_ung, con_lai = lay_han_muc_ung_luong(ma_nv, hien_tai.month, hien_tai.year)
    limit_info = {
        'luong_cb': luong_cb, 
        'da_ung': da_ung, 
        'max_50': luong_cb * 0.5, 
        'con_lai': con_lai
    }

    return render_template('admin/salary.html', 
                           bang_luong=bang_luong, 
                           limit_info=limit_info,
                           sel_thang=thang, 
                           sel_nam=nam, 
                           hien_tai=hien_tai)


# ==========================================
# --- ADMIN FEATURES ROUTES ---
# ==========================================
#--- QL NHÂN SỰ ---#
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
    
    # Lấy dữ liệu từ form
    ho_ten = request.form['ho_ten']
    tai_khoan = request.form['tai_khoan']
    mat_khau = request.form['mat_khau']
    luong = request.form['luong']
    gioi_tinh = request.form['gioi_tinh']
    ngay_sinh = request.form['ngay_sinh']
    
    # Các trường không bắt buộc
    sdt = request.form.get('sdt', '')
    email = request.form.get('email', '')
    chuc_vu = request.form['chuc_vu']
    phong_ban = request.form['phong_ban']
    
    if them_nhan_vien_moi(ho_ten, sdt, email, chuc_vu, luong, phong_ban, tai_khoan, mat_khau, gioi_tinh, ngay_sinh):
        flash('Thêm nhân viên thành công!', 'success')
    else:
        flash('Lỗi! Tên tài khoản đã tồn tại hoặc dữ liệu lỗi.', 'danger')
        
    return redirect(url_for('admin_nhan_su'))

@app.route('/admin/nhan_su/sua', methods=['POST'])
def admin_sua_nv():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    ma_nv = request.form['ma_nv']
    ho_ten = request.form['ho_ten']
    sdt = request.form.get('sdt', '')
    email = request.form.get('email', '')
    chuc_vu = request.form['chuc_vu']
    luong = request.form['luong']
    phong_ban = request.form['phong_ban']
    tai_khoan = request.form['tai_khoan']
    mat_khau = request.form['mat_khau']
    gioi_tinh = request.form['gioi_tinh']
    ngay_sinh = request.form['ngay_sinh']
    
    if cap_nhat_nhan_vien_admin(ma_nv, ho_ten, sdt, email, chuc_vu, luong, phong_ban, tai_khoan, mat_khau, gioi_tinh, ngay_sinh):
        flash('Cập nhật thành công!', 'success')
    else:
        flash('Lỗi cập nhật (Trùng tài khoản?)', 'danger')
        
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

#---QL Cham Công---#

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


#--- SALARY MANAGEMENT ---#

@app.route('/admin/quan_ly_luong')
def admin_ql_luong():
    if 'loggedin' not in session or session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']: 
        return redirect(url_for('login'))
    
    hien_tai = datetime.now()
    
    # Xử lý tham số 'all' từ URL
    req_month = request.args.get('month', str(hien_tai.month))
    thang = 'all' if req_month == 'all' else int(req_month)
    
    req_year = request.args.get('year', str(hien_tai.year))
    nam = 'all' if req_year == 'all' else int(req_year)
        
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
    

@app.route('/admin/export_quan_ly_luong')
def admin_export_quan_ly_luong():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    try:
        # 1. Lấy tham số filter
        hien_tai = datetime.now()
        req_month = request.args.get('month', str(hien_tai.month))
        thang = 'all' if req_month == 'all' else int(req_month)
        
        req_year = request.args.get('year', str(hien_tai.year))
        nam = 'all' if req_year == 'all' else int(req_year)
        
        keyword = request.args.get('keyword', '').strip()
        role = request.args.get('role', 'all')
        
        # 2. Lấy dữ liệu
        data = lay_ds_bang_luong_admin(thang, nam, keyword, role)
        
        # --- KIỂM TRA DỮ LIỆU ---
        if not data:
            flash("Không tìm thấy dữ liệu phù hợp để xuất file Excel!", "warning")
            # Redirect về trang quản lý kèm theo tham số cũ để không bị mất filter
            return redirect(url_for('admin_ql_luong', month=req_month, year=req_year, keyword=keyword, role=role))

        # 3. Tạo file Excel
        export_list = []
        for row in data:
            export_list.append({
                'Tháng': row['Thang'], 'Năm': row['Nam'],
                'Mã NV': row['MaNV'], 'Họ Tên': row['HoTen'],
                'Phòng Ban': row['TenPhongBan'],
                'Công Thực Tế': row['SoCongThucTe'],
                'Lương Cơ Bản': row['LuongCoBan'],
                'Thưởng': row['ThuongThem'], 'Phạt': row['Phat'],
                'Ứng Lương': row['UngLuong'], 'Nợ Cũ': row['NoCu'],
                'Thực Lĩnh': row['Tong'], 'Trạng Thái': row['TrangThai']
            })
        
        df = pd.DataFrame(export_list)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            sheet_name = f'Luong_{thang}_{nam}' if thang != 'all' else 'Tong_Hop'
            df.to_excel(writer, index=False, sheet_name=sheet_name[:30])
            
        output.seek(0)
        filename = f"QuanLy_Luong_{thang}_{nam}.xlsx"
        return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        flash(f"Lỗi khi xuất file: {str(e)}", "danger")
        return redirect(url_for('admin_ql_luong'))


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
    trang_thai = request.form['trang_thai'] # 'DaDuyet' hoặc 'TuChoi'
    admin_id = session.get('ma_nv')
    
    success, message = duyet_ung_luong(ma_yc, trang_thai, admin_id)
    
    if success:
        hanh_dong = "Duyệt" if trang_thai == 'DaDuyet' else "Từ chối"
        flash(f'Đã {hanh_dong} yêu cầu. {message}', 'success')
    else:
        # Hiển thị lỗi chi tiết ra màn hình để bạn biết nó sai ở đâu (VD: sai tên cột)
        flash(f'Lỗi xử lý: {message}', 'danger')
        
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

@app.route('/export_personal_salary')
def export_personal_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    # Lấy filter từ URL
    hien_tai = datetime.now()
    req_month = request.args.get('month', 'all')
    thang = int(req_month) if req_month != 'all' else 'all'
    
    req_year = request.args.get('year', str(hien_tai.year))
    nam = int(req_year) if req_year != 'all' else 'all'
    
    # Lấy dữ liệu
    data = lay_bang_luong(ma_nv, thang, nam)
    
    if not data:
        flash("Không có dữ liệu lương để xuất!", 'warning')
        # Redirect về đúng trang người dùng đang đứng
        referer = request.headers.get("Referer")
        return redirect(referer if referer else url_for('employee_salary'))

    # Tạo Excel
    export_list = []
    for row in data:
        export_list.append({
            'Tháng': row['Thang'],
            'Năm': row['Nam'],
            'Lương Cơ Bản': row['LuongCoBan'],
            'Thưởng': row['ThuongThem'],
            'Phạt': row['Phat'],
            'Ứng Lương': row['UngLuong'],
            'Thực Lĩnh': row['Tong'],
            'Ngày Tạo': row['NgayTao'],
            'Trạng Thái': row['TrangThai']
        })
        
    df = pd.DataFrame(export_list)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        sheet_name = f'Luong_CN_{thang}_{nam}'
        df.to_excel(writer, index=False, sheet_name=sheet_name[:30])
        
    output.seek(0)
    filename = f"Lich_Su_Luong_{ma_nv}_{thang}_{nam}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')



if __name__ == '__main__':
    app.run(debug=True)
