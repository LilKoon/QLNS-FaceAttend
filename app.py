from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
import calendar
from datetime import datetime, timedelta
from ham import *;
import csv
import io

app = Flask(__name__)
app.secret_key = '06430313' 

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
            
            role = user['role_id']
            if role == 'QuanLyCapCao' or role == 'QuanLyCapThap': 
                return redirect(url_for('admin_trangchu'))
            elif role == 'NhanVien':
                return redirect(url_for('employee_trangchu'))
            else:
                flash('Quyền không hợp lệ', 'warning')
                return redirect(url_for('login'))
        else:
            flash('Sai tài khoản hoặc mật khẩu', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# --- BACKEND CHO EMPLOYEE ---
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
        status_color = "warning"
    elif cham_cong['CheckIn'] and not cham_cong['CheckOut']:
        gio_vao = cham_cong['CheckIn'].strftime('%H:%M')
        status_msg = f"Đã Check-in lúc {gio_vao}. Đang trong giờ làm việc."
        status_color = "info"
    elif cham_cong['CheckIn'] and cham_cong['CheckOut']:
        gio_ra = cham_cong['CheckOut'].strftime('%H:%M')
        status_msg = f"Đã hoàn thành công việc (Về lúc {gio_ra})."
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

# --- XEM BẢNG LƯƠNG ---
@app.route('/employee/salary')
def employee_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    # Lấy tham số lọc
    thang_loc = request.args.get('month')
    nam_loc = request.args.get('year')
    
    if thang_loc and nam_loc and thang_loc != 'all':
        thang_loc = int(thang_loc)
        nam_loc = int(nam_loc)
        bang_luong = lay_bang_luong(ma_nv, thang_loc, nam_loc)
    else:
        thang_loc = None
        nam_loc = None
        bang_luong = lay_bang_luong(ma_nv)
    
    nam_hien_tai = datetime.now().year
    
    return render_template('employee/salary.html', 
                           bang_luong=bang_luong, 
                           sel_thang=thang_loc, 
                           sel_nam=nam_loc,
                           nam_hien_tai=nam_hien_tai)

# --- XUẤT EXCEL (ĐÃ SỬA LỖI NAMEERROR) ---
@app.route('/employee/export_salary')
def export_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    export_type = request.args.get('type', 'all')
    
    # 1. LẤY DỮ LIỆU TỪ DB
    if export_type == 'filter':
        try:
            thang = int(request.args.get('month'))
            nam = int(request.args.get('year'))
            data = lay_bang_luong(ma_nv, thang, nam)
            filename = f"Bang_Luong_T{thang}_{nam}.csv"
            msg_error = f"Không tìm thấy dữ liệu lương tháng {thang}/{nam} để xuất!"
        except (ValueError, TypeError):
            # Nếu tham số lỗi thì báo lỗi luôn
            flash('Tham số tháng/năm không hợp lệ!', 'danger')
            return redirect(url_for('employee_salary'))
    else:
        # Xuất toàn bộ
        data = lay_bang_luong(ma_nv)
        filename = "Lich_Su_Luong_Day_Du.csv"
        msg_error = "Bạn chưa có lịch sử lương nào để xuất!"

    # 2. KIỂM TRA QUAN TRỌNG: NẾU KHÔNG CÓ DỮ LIỆU -> CHẶN LẠI
    if not data:
        flash(msg_error, 'warning') # Hiện thông báo màu vàng
        # Quay trở lại trang bảng lương ngay lập tức
        return redirect(url_for('employee_salary'))

    # 3. NẾU CÓ DỮ LIỆU -> TIẾP TỤC TẠO FILE CSV
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Ghi BOM để Excel hiển thị tiếng Việt
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
        
    # 4. TẠO RESPONSE (Hàm này cần được import từ flask)
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

    attend_data = lay_du_lieu_cham_cong_thang(ma_nv, thang, nam)
    cal = calendar.monthcalendar(nam, thang)
    
    return render_template('employee/attendlog.html', 
                           calendar=cal, 
                           attend_data=attend_data, 
                           thang=thang, 
                           nam=nam)

@app.route('/employee/schedule')
def employee_schedule():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    # 1. Xác định ngày hôm nay và Thứ 2 đầu tuần
    hom_nay = datetime.now()
    # weekday(): 0 là Thứ 2, 6 là CN -> Trừ đi số ngày lẻ để về Thứ 2
    thu_hai = hom_nay - timedelta(days=hom_nay.weekday())
    
    # 2. Tạo danh sách 7 ngày trong tuần để hiển thị tiêu đề cột
    # (Format: [{'date': datetime, 'label': 'Thứ 2'}, ...])
    danh_sach_ngay = []
    ten_thu = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    
    for i in range(7):
        ngay = thu_hai + timedelta(days=i)
        danh_sach_ngay.append({
            'date_obj': ngay, # Dùng để so sánh
            'date_str': ngay.strftime('%Y-%m-%d'), # Dùng để tra cứu trong dict
            'display': ngay.strftime('%d/%m'), # Hiển thị 25/11
            'day_name': ten_thu[i]
        })
    
    # 3. Lấy dữ liệu từ DB (Từ Thứ 2 -> Chủ Nhật)
    cn = thu_hai + timedelta(days=6)
    du_lieu_lich = lay_lich_lam_viec(ma_nv, thu_hai.strftime('%Y-%m-%d'), cn.strftime('%Y-%m-%d'))
    
    return render_template('employee/schedule.html', 
                           days=danh_sach_ngay, 
                           schedule=du_lieu_lich,
                           hom_nay_str=hom_nay.strftime('%Y-%m-%d'))

# ==========================================
# --- BACKEND CHO ADMIN ---
# ==========================================
@app.route('/admin/TrangChu')
def admin_trangchu():
    if 'loggedin' not in session: return redirect(url_for('login'))
    # (Bạn nhớ import các hàm lay_thong_ke... ở đầu file nếu chưa có)
    # Ở đây tôi giả định bạn đã có các hàm stats từ bước trước, nếu chưa thì chỉ render template
    from ham import lay_thong_ke_dashboard, lay_hoat_dong_gan_day 
    stats = lay_thong_ke_dashboard()
    activities = lay_hoat_dong_gan_day()
    return render_template('admin/trangchu.html', stats=stats, activities=activities)

# --- ROUTE MỚI: TRANG CHỦ CÁ NHÂN CỦA ADMIN (Giống Employee Home) ---
@app.route('/admin/personal_home')
def admin_personal_home():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']:
        return redirect(url_for('employee_trangchu'))

    ma_nv = session.get('ma_nv')
    
    cham_cong = lay_trang_thai_cham_cong_hom_nay(ma_nv)
    
    status_msg = ""
    status_color = "warning"
    if not cham_cong:
        status_msg = "Bạn chưa thực hiện chấm công hôm nay."
        status_color = "warning"
    elif cham_cong['CheckIn'] and not cham_cong['CheckOut']:
        gio_vao = cham_cong['CheckIn'].strftime('%H:%M')
        status_msg = f"Đã Check-in lúc {gio_vao}. Đang trong giờ làm việc."
        status_color = "info"
    elif cham_cong['CheckIn'] and cham_cong['CheckOut']:
        gio_ra = cham_cong['CheckOut'].strftime('%H:%M')
        status_msg = f"Hoàn thành công việc (Về lúc {gio_ra})."
        status_color = "success"

    # Render template riêng trong thư mục admin
    return render_template('admin/personal_home.html', cham_cong=cham_cong, msg=status_msg, color=status_color)


@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    # Kiểm tra quyền Admin
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

    # Lấy thông tin hiển thị
    info = lay_thong_tin_nhan_vien(ma_nv)
    return render_template('admin/profile.html', info=info)

@app.route('/admin/salary')
def admin_salary():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    # Kiểm tra quyền Admin
    if session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']:
        return redirect(url_for('employee_salary'))

    ma_nv = session.get('ma_nv')
    
    thang_loc = request.args.get('month')
    nam_loc = request.args.get('year')
    
    if thang_loc and nam_loc and thang_loc != 'all':
        thang_loc = int(thang_loc)
        nam_loc = int(nam_loc)
        bang_luong = lay_bang_luong(ma_nv, thang_loc, nam_loc)
    else:
        thang_loc = None
        nam_loc = None
        bang_luong = lay_bang_luong(ma_nv)
    
    nam_hien_tai = datetime.now().year
    
    # Render template trong thư mục ADMIN
    return render_template('admin/salary.html', 
                           bang_luong=bang_luong, 
                           sel_thang=thang_loc, 
                           sel_nam=nam_loc,
                           nam_hien_tai=nam_hien_tai)

# 2. Xuất Excel Lương Cá Nhân (Cho Admin)
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
        cw.writerow([f"Tháng {row['Thang']}", row['Nam'], "{:,.0f}".format(row['LuongCoBan']), "{:,.0f}".format(row['ThuongThem']), "{:,.0f}".format(row['Phat']), "{:,.0f}".format(row['Tong']), row['TrangThai'], row['NgayTao']])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv; charset=utf-8-sig"
    return output

# 3. Xem Lịch Sử Chấm Công Cá Nhân
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

    attend_data = lay_du_lieu_cham_cong_thang(ma_nv, thang, nam)
    cal = calendar.monthcalendar(nam, thang)
    
    return render_template('admin/attendlog.html', calendar=cal, attend_data=attend_data, thang=thang, nam=nam)

# 4. Xem Lịch Làm Việc Cá Nhân
@app.route('/admin/schedule')
def admin_schedule():
    if 'loggedin' not in session: return redirect(url_for('login'))
    ma_nv = session.get('ma_nv')
    
    hom_nay = datetime.now()
    thu_hai = hom_nay - timedelta(days=hom_nay.weekday())
    danh_sach_ngay = []
    ten_thu = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"]
    for i in range(7):
        ngay = thu_hai + timedelta(days=i)
        danh_sach_ngay.append({'date_obj': ngay, 'date_str': ngay.strftime('%Y-%m-%d'), 'display': ngay.strftime('%d/%m'), 'day_name': ten_thu[i]})
    
    cn = thu_hai + timedelta(days=6)
    du_lieu_lich = lay_lich_lam_viec(ma_nv, thu_hai.strftime('%Y-%m-%d'), cn.strftime('%Y-%m-%d'))
    
    return render_template('admin/schedule.html', days=danh_sach_ngay, schedule=du_lieu_lich, hom_nay_str=hom_nay.strftime('%Y-%m-%d'))

# 5. Quản Lý Nhân Sự
@app.route('/admin/nhan_su')
def admin_nhan_su():
    if 'loggedin' not in session or session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']:
        return redirect(url_for('login'))
    
    # 1. Lấy dữ liệu từ thanh tìm kiếm (GET params)
    keyword = request.args.get('keyword', '').strip()
    
    # Lấy danh sách các checkbox được tích (name="filters")
    filters = request.args.getlist('filters') 
    
    # 2. Gọi hàm tìm kiếm mới
    ds_nv = lay_danh_sach_nhan_vien(keyword, filters)
    ds_pb = lay_danh_sach_phong_ban()
    
    # Trả về template kèm theo thông tin đã tìm kiếm để giữ trạng thái form
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
    
    # Lấy thêm tài khoản/mật khẩu
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
    
    # Lấy thêm tài khoản/mật khẩu để cập nhật
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
    
    # Không cho phép tự xóa chính mình
    if ma_nv == session.get('ma_nv'):
        flash('Bạn không thể tự xóa tài khoản của mình!', 'warning')
        return redirect(url_for('admin_nhan_su'))

    if xoa_nhan_vien(ma_nv):
        flash('Đã xóa nhân viên khỏi hệ thống!', 'success')
    else:
        flash('Lỗi khi xóa nhân viên!', 'danger')
        
    return redirect(url_for('admin_nhan_su'))


#     # Cham Cong
@app.route('/admin/cham_cong')
def admin_ql_cham_cong():
    if 'loggedin' not in session or session.get('role_id') not in ['QuanLyCapCao', 'QuanLyCapThap']:
        return redirect(url_for('login'))
    
    # Lấy ngày từ tham số URL, nếu không có thì lấy ngày hôm nay
    ngay_chon = request.args.get('date')
    if not ngay_chon:
        ngay_chon = datetime.now().strftime('%Y-%m-%d')
        
    ds_cong = lay_bang_cham_cong_ngay(ngay_chon)
    
    return render_template('admin/qlChamCong.html', ds_cong=ds_cong, ngay_chon=ngay_chon)

@app.route('/admin/cham_cong/sua', methods=['POST'])
def admin_sua_cc():
    if 'loggedin' not in session: return redirect(url_for('login'))
    
    log_id = request.form['log_id']
    gio_vao = request.form['gio_vao'] # Dạng HH:mm:ss
    gio_ra = request.form['gio_ra']
    ngay_chon = request.form['ngay_chon'] # Để ghép thành datetime
    
    if admin_sua_cham_cong(log_id, gio_vao, gio_ra, ngay_chon):
        flash('Đã cập nhật giờ chấm công thành công!', 'success')
    else:
        flash('Lỗi cập nhật!', 'danger')
        
    # Quay lại đúng ngày đang xem
    return redirect(url_for('admin_ql_cham_cong', date=ngay_chon))

#     #Tinh Luong
# @app.route('/admin/salary_management')
    
#     #Xep Ca
# @app .route('/admin/schedule_management')




if __name__ == '__main__':
    app.run(debug=True)