import pyodbc
from werkzeug.security import check_password_hash, generate_password_hash 
from datetime import datetime, timedelta
import calendar

# --- Cấu hình kết nối MS SQL Server ---
def get_db_connection():
    DB_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=LilKoon;"
    "DATABASE=QLNS;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(DB_CONN_STR)

# --- 1. XÁC THỰC & TÀI KHOẢN ---
# ==========================================

def kiem_tra_dang_nhap(username, password):
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        query = "SELECT MaNV, TaiKhoan, MatKhau, RoleID FROM Account WHERE TaiKhoan = ?"
        cursor.execute(query, (username,))
        row = cursor.fetchone()
        
        if row:
            # Kiểm tra mật khẩu (Hiện tại đang so sánh chuỗi thường theo DB cũ)
            # Nếu sau này dùng hash: if check_password_hash(row.MatKhau, password):
            if row.MatKhau == password:
                return {'ma_nv': row.MaNV, 'tai_khoan': row.TaiKhoan, 'role_id': row.RoleID}
        return None
    finally:
        conn.close()

def doi_mat_khau(ma_nv, mat_khau_cu, mat_khau_moi):
    conn = get_db_connection()
    if not conn: return False, "Lỗi kết nối CSDL"
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MatKhau FROM Account WHERE MaNV = ?", (ma_nv,))
        row = cursor.fetchone()
        if not row: return False, "Tài khoản không tồn tại"
        
        if row.MatKhau != mat_khau_cu:
             return False, "Mật khẩu cũ không chính xác!"

        # Cập nhật mật khẩu mới
        cursor.execute("UPDATE Account SET MatKhau = ? WHERE MaNV = ?", (mat_khau_moi, ma_nv))
        conn.commit()
        return True, "Đổi mật khẩu thành công!"
    except Exception as e:
        print(f"Lỗi đổi mật khẩu: {e}")
        return False, "Có lỗi xảy ra khi đổi mật khẩu."
    finally:
        conn.close()

# ==========================================
# --- 2. QUẢN LÝ HỒ SƠ (PROFILE) ---
# ==========================================

def lay_thong_tin_nhan_vien(ma_nv):
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        query = """
        SELECT e.MaNV, e.HoTen, e.NamSinh, e.DiaChi, e.SoDienThoai, e.email, e.LuongCoBan, 
               e.RoleID as ChucVu, e.NgayVaoLam,
               p.TenPhongBan
        FROM Employee e
        LEFT JOIN PhongBan p ON e.PhongBanID = p.PhongBanID
        WHERE e.MaNV = ?
        """
        cursor.execute(query, (ma_nv,))
        row = cursor.fetchone()
        if row:
            ngay_vao = row.NgayVaoLam.strftime('%d/%m/%Y') if row.NgayVaoLam else "Chưa cập nhật"
            phong_ban = row.TenPhongBan if row.TenPhongBan else "Chưa phân phòng"
            
            return {
                'MaNV': row.MaNV, 'HoTen': row.HoTen, 'NamSinh': row.NamSinh, 
                'DiaChi': row.DiaChi, 'SoDienThoai': row.SoDienThoai, 'Email': row.email, 
                'LuongCoBan': row.LuongCoBan, 'ChucVu': row.ChucVu, 
                'TenPhongBan': phong_ban, 'NgayVaoLam': ngay_vao 
            }
        return None
    finally:
        conn.close()

def cap_nhat_profile(ma_nv, sdt, email, dia_chi):
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        query = "UPDATE Employee SET SoDienThoai = ?, email = ?, DiaChi = ? WHERE MaNV = ?"
        cursor.execute(query, (sdt, email, dia_chi, ma_nv))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi update profile: {e}")
        return False
    finally:
        conn.close()

# ==========================================
# --- 3. CHẤM CÔNG (ATTENDANCE) ---
# ==========================================

def lay_trang_thai_cham_cong_hom_nay(ma_nv):
    conn = get_db_connection()
    if not conn: return None
    try:
        cursor = conn.cursor()
        query = """
        SELECT CheckIn, CheckOut 
        FROM AttendLog 
        WHERE MaNV = ? AND CAST(CheckIn AS DATE) = CAST(GETDATE() AS DATE)
        """
        cursor.execute(query, (ma_nv,))
        row = cursor.fetchone()
        if row:
            return {'CheckIn': row.CheckIn, 'CheckOut': row.CheckOut}
        return None
    finally:
        conn.close()

def lay_bang_cham_cong_ngay(ngay_xem, tu_khoa=''):
    """Lấy bảng công ngày để Admin xem"""
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        query = """
        SELECT a.LogId, e.MaNV, e.HoTen, p.TenPhongBan, a.CheckIn, a.CheckOut, 
               c.TenCa, c.GioBatDau, c.GioKetThuc
        FROM AttendLog a 
        JOIN Employee e ON a.MaNV = e.MaNV 
        LEFT JOIN PhongBan p ON e.PhongBanID = p.PhongBanID
        LEFT JOIN PhanCa pc ON e.MaNV = pc.MaNV AND pc.NgayLamViec = CAST(a.CheckIn AS DATE)
        LEFT JOIN CaLamViec c ON pc.MaCa = c.MaCa
        WHERE CAST(a.CheckIn AS DATE) = ?
        """
        params = [ngay_xem]
        if tu_khoa:
            search_term = f"%{tu_khoa}%"
            query += " AND (e.HoTen LIKE ? OR CAST(e.MaNV AS NVARCHAR) LIKE ?)"
            params.extend([search_term, search_term])
        query += " ORDER BY a.CheckIn DESC"
        
        cursor.execute(query, tuple(params))
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            # Format
            item['GioVao'] = item['CheckIn'].strftime('%H:%M:%S') if item['CheckIn'] else ""
            item['GioRa'] = item['CheckOut'].strftime('%H:%M:%S') if item['CheckOut'] else ""
            
            # Logic Trạng Thái
            trang_thai = []
            color = 'success'
            if item['GioBatDau'] and item['GioKetThuc']:
                base_date = item['CheckIn'].date()
                start_time = datetime.combine(base_date, item['GioBatDau'])
                end_time = datetime.combine(base_date, item['GioKetThuc'])
                
                if item['CheckIn'] > start_time + timedelta(minutes=15): 
                    trang_thai.append("Đi muộn"); color = 'warning text-dark'
                if item['CheckOut']:
                    if item['CheckOut'] < end_time: 
                        trang_thai.append("Về sớm"); color = 'warning text-dark'
                else:
                    trang_thai.append("Chưa về"); color = 'secondary'
                
                if not trang_thai: trang_thai = ["Oke"]
            else:
                trang_thai = ["Làm không lịch"]; color = 'info text-dark'
            
            item['TrangThai'] = ", ".join(trang_thai)
            item['Color'] = color
            item['TenCa'] = item['TenCa'] if item['TenCa'] else "Không xác định"
            results.append(item)
        return results
    except Exception as e: 
        print(e); return []
    finally: conn.close()

def lay_du_lieu_cham_cong_thang(ma_nv, thang, nam):
    """Lấy dữ liệu để hiển thị lên Lịch (Calendar)"""
    conn = get_db_connection()
    if not conn: return {}
    data_cham_cong = {}
    try:
        cursor = conn.cursor()
        # 1. Dữ liệu đi làm
        cursor.execute("SELECT DAY(CheckIn) as Ngay, CheckIn, CheckOut FROM AttendLog WHERE MaNV = ? AND MONTH(CheckIn) = ? AND YEAR(CheckIn) = ?", (ma_nv, thang, nam))
        for row in cursor.fetchall():
            gio_vao = row.CheckIn.strftime('%H:%M') if row.CheckIn else "--:--"
            gio_ra = row.CheckOut.strftime('%H:%M') if row.CheckOut else "--:--"
            color_status = 'warning' if row.CheckIn and not row.CheckOut else 'success'
            data_cham_cong[row.Ngay] = {'check_in': gio_vao, 'check_out': gio_ra, 'color': color_status}
        
        # 2. Dữ liệu xin nghỉ
        cursor.execute("SELECT DAY(NgayCanNghi) as Ngay FROM YeuCau WHERE MaNV = ? AND MONTH(NgayCanNghi) = ? AND YEAR(NgayCanNghi) = ? AND LoaiYeuCau = 'XIN_NGHI' AND TrangThai = N'DaDuyet'", (ma_nv, thang, nam))
        for row in cursor.fetchall():
            if row.Ngay not in data_cham_cong:
                data_cham_cong[row.Ngay] = {'check_in': 'Nghỉ Phép', 'check_out': '', 'color': 'dark'}
        return data_cham_cong
    finally: conn.close()

def admin_sua_cham_cong(log_id, gio_vao, gio_ra, ngay_chon, admin_id):
    """Sửa giờ công và Ghi Log"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT CheckIn, CheckOut FROM AttendLog WHERE LogId = ?", (log_id,))
        row = cursor.fetchone()
        old_in = row.CheckIn.strftime('%H:%M') if row and row.CheckIn else "None"
        old_out = row.CheckOut.strftime('%H:%M') if row and row.CheckOut else "None"
        
        dt_vao = f"{ngay_chon} {gio_vao}" if gio_vao else None
        dt_ra = f"{ngay_chon} {gio_ra}" if gio_ra else None
        cursor.execute("UPDATE AttendLog SET CheckIn = ?, CheckOut = ? WHERE LogId = ?", (dt_vao, dt_ra, log_id))
        
        # Ghi Log
        msg = f"Sửa Log {log_id}: Vào ({old_in}->{gio_vao}), Ra ({old_out}->{gio_ra})"
        cursor.execute("INSERT INTO AuditLog (NguoiSua, BangAnhHuong, IdBanGhi, HanhDong, ThoiGian) VALUES (?, 'AttendLog', ?, ?, GETDATE())", (admin_id, log_id, msg))
        conn.commit()
        return True
    except Exception as e:
        print(e); return False
    finally: conn.close()

# ==========================================
# --- 4. LƯƠNG (PAYROLL) ---
# ==========================================

def lay_bang_luong(ma_nv, thang=None, nam=None):
    """Lấy bảng lương cho nhân viên xem"""
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM Salary WHERE MaNV = ?"
        params = [ma_nv]
        if thang and nam:
            query += " AND Thang = ? AND Nam = ?"
            params.extend([thang, nam])
        query += " ORDER BY Nam DESC, Thang DESC"
        cursor.execute(query, tuple(params))
        
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            if item.get('NgayTao'): item['NgayTao'] = item['NgayTao'].strftime('%d/%m/%Y')
            results.append(item)
        return results
    finally: conn.close()

def lay_ds_bang_luong_admin(thang, nam, tu_khoa='', chuc_vu=''):
    """Lấy bảng lương cho Admin xem (kèm tên, phòng ban, lọc)"""
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        query = """
        SELECT s.*, e.HoTen, e.SoDienThoai, p.TenPhongBan, e.RoleID 
        FROM Salary s 
        JOIN Employee e ON s.MaNV = e.MaNV 
        LEFT JOIN PhongBan p ON e.PhongBanID = p.PhongBanID 
        WHERE s.Thang = ? AND s.Nam = ?
        """
        params = [thang, nam]
        if tu_khoa:
            search = f"%{tu_khoa}%"
            query += " AND (e.HoTen LIKE ? OR CAST(e.MaNV AS NVARCHAR) LIKE ?)"
            params.extend([search, search])
        if chuc_vu and chuc_vu != 'all':
            query += " AND e.RoleID = ?"
            params.append(chuc_vu)
            
        query += " ORDER BY s.SalaryId DESC"
        cursor.execute(query, tuple(params))
        
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            for key in ['LuongCoBan', 'ThuongThem', 'Phat', 'UngLuong', 'NoCu', 'Tong']:
                val = item.get(key) or 0
                item[f'{key}_Fmt'] = "{:,.0f}".format(val)
            if item.get('SoCongThucTe'): item['SoCongThucTe'] = round(item['SoCongThucTe'], 2)
            results.append(item)
        return results
    finally: conn.close()

def tinh_toan_va_luu_luong(thang, nam):
    """Logic tính toán lương tự động"""
    conn = get_db_connection()
    if not conn: return False, "Lỗi kết nối DB"
    try:
        cursor = conn.cursor()
        # Xác định tháng trước để tìm nợ
        thang_truoc = thang - 1
        nam_truoc = nam
        if thang_truoc == 0: thang_truoc = 12; nam_truoc = nam - 1
        
        so_ngay = calendar.monthrange(nam, thang)[1]
        cong_chuan = (so_ngay - 4) * 8
        
        cursor.execute("SELECT MaNV, LuongCoBan FROM Employee")
        nv_list = cursor.fetchall()
        count = 0
        for nv in nv_list:
            ma_nv = nv.MaNV; luong_cb = nv.LuongCoBan or 0
            
            # Tính công
            cursor.execute("SELECT SUM(DATEDIFF(MINUTE, CheckIn, CheckOut)) FROM AttendLog WHERE MaNV = ? AND MONTH(CheckIn) = ? AND YEAR(CheckIn) = ? AND CheckOut IS NOT NULL", (ma_nv, thang, nam))
            res_gio = cursor.fetchone()
            tong_gio = (res_gio[0] / 60.0) if res_gio[0] else 0
            
            luong_cong = (float(luong_cb) / cong_chuan) * tong_gio if cong_chuan > 0 else 0
            luong_theo_cong = round(luong_theo_cong)

            # Tìm nợ cũ
            cursor.execute("SELECT Tong FROM Salary WHERE MaNV = ? AND Thang = ? AND Nam = ?", (ma_nv, thang_truoc, nam_truoc))
            row_prev = cursor.fetchone()
            no_cu = abs(row_prev.Tong) if row_prev and row_prev.Tong < 0 else 0
            
            # Update/Insert
            cursor.execute("SELECT SalaryId, ThuongThem, Phat, UngLuong FROM Salary WHERE MaNV = ? AND Thang = ? AND Nam = ?", (ma_nv, thang, nam))
            row_sal = cursor.fetchone()
            if row_sal:
                thuong = row_sal.ThuongThem or 0; phat = row_sal.Phat or 0; ung = row_sal.UngLuong or 0
                tong = round(luong_cong + float(thuong) - float(phat) - float(ung) - float(no_cu))
                cursor.execute("UPDATE Salary SET LuongCoBan=?, SoCongChuan=?, SoCongThucTe=?, NoCu=?, Tong=?, NgayTao=GETDATE() WHERE SalaryId=?", (luong_cb, cong_chuan, tong_gio, no_cu, tong, row_sal.SalaryId))
            else:
                tong = round(luong_cong - float(no_cu))
                cursor.execute("INSERT INTO Salary (MaNV, Thang, Nam, LuongCoBan, SoCongChuan, SoCongThucTe, ThuongThem, Phat, UngLuong, NoCu, Tong, TrangThai, NgayTao) VALUES (?,?,?,?,?,?,0,0,0,?,?,N'Chờ duyệt',GETDATE())", (ma_nv, thang, nam, luong_cb, cong_chuan, tong_gio, no_cu, tong))
            count += 1
        conn.commit()
        return True, f"Đã tính cho {count} người"
    except Exception as e:
        return False, str(e)
    finally: conn.close()

def cap_nhat_thuong_phat(salary_id, thuong, phat, ung_luong, admin_id):
    """Sửa thủ công Thưởng/Phạt/Ứng -> Tính lại Tổng"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT s.*, e.HoTen FROM Salary s JOIN Employee e ON s.MaNV = e.MaNV WHERE s.SalaryId = ?", (salary_id,))
        row = cursor.fetchone()
        if not row: return False
        
        luong_cb = float(row.LuongCoBan); cong_chuan = float(row.SoCongChuan); thuc_te = float(row.SoCongThucTe); no_cu = float(row.NoCu or 0)
        luong_cong = (luong_cb / cong_chuan) * thuc_te if cong_chuan > 0 else 0
        
        tong_moi = round(luong_cong + float(thuong) - float(phat) - float(ung_luong) - no_cu)
        
        cursor.execute("UPDATE Salary SET ThuongThem=?, Phat=?, UngLuong=?, Tong=? WHERE SalaryId=?", (thuong, phat, ung_luong, tong_moi, salary_id))
        
        # Ghi Log nếu đã thanh toán rồi mà vẫn sửa
        if row.TrangThai == 'Đã thanh toán':
            changes = []
            old_thuong = row.ThuongThem or 0; old_phat = row.Phat or 0; old_ung = row.UngLuong or 0
            if float(thuong) != float(old_thuong): changes.append(f"Thưởng: {old_thuong:,.0f}->{int(thuong):,.0f}")
            if float(phat) != float(old_phat): changes.append(f"Phạt: {old_phat:,.0f}->{int(phat):,.0f}")
            if float(ung_luong) != float(old_ung): changes.append(f"Ứng: {old_ung:,.0f}->{int(ung_luong):,.0f}")
            
            if changes:
                msg = f"Sửa lương T{row.Thang}/{row.Nam} của {row.HoTen}: " + ", ".join(changes)
                cursor.execute("INSERT INTO AuditLog (NguoiSua, BangAnhHuong, IdBanGhi, HanhDong, ThoiGian) VALUES (?, 'Salary', ?, ?, GETDATE())", (admin_id, salary_id, msg))
        
        conn.commit()
        return True
    except Exception as e:
        print(e); return False
    finally: conn.close()

def duyet_thanh_toan_luong(salary_id):
    """Duyệt từng người"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Salary SET TrangThai = N'Đã thanh toán' WHERE SalaryId = ?", (salary_id,))
        conn.commit(); return True
    finally: conn.close()

def duyet_tat_ca_luong_thang(thang, nam, tu_khoa='', chuc_vu=''):
    """Duyệt hàng loạt theo bộ lọc"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        query = "UPDATE s SET s.TrangThai = N'Đã thanh toán' FROM Salary s JOIN Employee e ON s.MaNV = e.MaNV WHERE s.Thang = ? AND s.Nam = ? AND s.TrangThai = N'Chờ duyệt'"
        params = [thang, nam]
        if tu_khoa:
            search = f"%{tu_khoa}%"
            query += " AND (e.HoTen LIKE ? OR CAST(e.MaNV AS NVARCHAR) LIKE ?)"
            params.extend([search, search])
        if chuc_vu and chuc_vu != 'all':
            query += " AND e.RoleID = ?"
            params.append(chuc_vu)
        cursor.execute(query, tuple(params))
        conn.commit()
        return True
    finally: conn.close()

# ==========================================
# --- 5. QUẢN LÝ NHÂN SỰ (ADMIN) ---
# ==========================================

def lay_danh_sach_nhan_vien(tu_khoa='', cac_truong=None):
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        query = """
        SELECT e.MaNV, e.HoTen, e.NamSinh, e.SoDienThoai, e.email, e.LuongCoBan, 
               e.RoleID as ChucVu, e.NgayVaoLam, p.TenPhongBan,
               a.TaiKhoan, a.MatKhau
        FROM Employee e
        LEFT JOIN PhongBan p ON e.PhongBanID = p.PhongBanID
        LEFT JOIN Account a ON e.MaNV = a.MaNV
        WHERE 1=1 
        """
        params = []
        if tu_khoa:
            search = f"%{tu_khoa}%"
            conds = []
            mapping = {'ma_nv': 'CAST(e.MaNV AS NVARCHAR)', 'ho_ten': 'e.HoTen', 'chuc_vu': 'e.RoleID', 'phong_ban': 'p.TenPhongBan'}
            if cac_truong:
                for f in cac_truong:
                    if f in mapping: conds.append(f"{mapping[f]} LIKE ?"); params.append(search)
            else:
                for c in mapping.values(): conds.append(f"{c} LIKE ?"); params.append(search)
            if conds: query += " AND (" + " OR ".join(conds) + ")"
            
        query += " ORDER BY e.MaNV DESC"
        cursor.execute(query, tuple(params))
        
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            if item.get('LuongCoBan'): item['LuongCoBan'] = "{:,.0f}".format(item['LuongCoBan'])
            if item.get('NgayVaoLam'): item['NgayVaoLam'] = item['NgayVaoLam'].strftime('%d/%m/%Y')
            if not item.get('TaiKhoan'): item['TaiKhoan'] = ''; item['MatKhau'] = ''
            results.append(item)
        return results
    finally: conn.close()

def them_nhan_vien_moi(ho_ten, sdt, email, chuc_vu, luong, phong_ban_id, tai_khoan, mat_khau):
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Employee (HoTen, SoDienThoai, email, RoleID, LuongCoBan, PhongBanID, NgayVaoLam) OUTPUT INSERTED.MaNV VALUES (?, ?, ?, ?, ?, ?, GETDATE())", (ho_ten, sdt, email, chuc_vu, luong, phong_ban_id))
        ma_nv = cursor.fetchone()[0]
        cursor.execute("INSERT INTO Account (MaNV, TaiKhoan, MatKhau, RoleID) VALUES (?, ?, ?, ?)", (ma_nv, tai_khoan, mat_khau, chuc_vu))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def cap_nhat_nhan_vien_admin(ma_nv, ho_ten, sdt, email, chuc_vu, luong, phong_ban_id, tai_khoan, mat_khau):
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Employee SET HoTen=?, SoDienThoai=?, email=?, RoleID=?, LuongCoBan=?, PhongBanID=? WHERE MaNV=?", (ho_ten, sdt, email, chuc_vu, luong, phong_ban_id, ma_nv))
        
        cursor.execute("SELECT COUNT(*) FROM Account WHERE MaNV = ?", (ma_nv,))
        if cursor.fetchone()[0]:
            cursor.execute("UPDATE Account SET TaiKhoan=?, MatKhau=?, RoleID=? WHERE MaNV=?", (tai_khoan, mat_khau, chuc_vu, ma_nv))
        else:
            cursor.execute("INSERT INTO Account (MaNV, TaiKhoan, MatKhau, RoleID) VALUES (?, ?, ?, ?)", (ma_nv, tai_khoan, mat_khau, chuc_vu))
        
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def xoa_nhan_vien(ma_nv):
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        for t in ['Account','Salary','AttendLog','PhanCa','FaceData','YeuCau','AuditLog']:
             try: cursor.execute(f"DELETE FROM {t} WHERE MaNV=?", (ma_nv,))
             except: pass
        cursor.execute("DELETE FROM Employee WHERE MaNV=?", (ma_nv,))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def lay_danh_sach_phong_ban():
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT PhongBanID, TenPhongBan FROM PhongBan")
        return [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
    finally: conn.close()

# ==========================================
# --- 6. LỊCH & YÊU CẦU (REQUESTS) ---
# ==========================================

def lay_danh_sach_ca_lam():
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor(); cursor.execute("SELECT * FROM CaLamViec")
        return [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
    finally: conn.close()

def lay_lich_lam_viec(ma_nv, start, end):
    conn = get_db_connection(); lich_data = {}
    if not conn: return {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.NgayLamViec, c.TenCa, c.GioBatDau, c.GioKetThuc FROM PhanCa p JOIN CaLamViec c ON p.MaCa = c.MaCa WHERE p.MaNV = ? AND p.NgayLamViec BETWEEN ? AND ?", (ma_nv, start, end))
        for row in cursor.fetchall():
            ngay_str = row.NgayLamViec.strftime('%Y-%m-%d')
            gbd = row.GioBatDau.strftime('%H:%M') if row.GioBatDau else ""
            gkt = row.GioKetThuc.strftime('%H:%M') if row.GioKetThuc else ""
            lich_data[ngay_str] = {'TenCa': row.TenCa, 'GioBatDau': gbd, 'GioKetThuc': gkt}
        return lich_data
    finally: conn.close()

def xep_ca_tu_dong(start, end):
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MaNV FROM Employee"); nvs = [r.MaNV for r in cursor.fetchall()]
        cursor.execute("SELECT TOP 1 MaCa FROM CaLamViec"); ca = cursor.fetchone()[0]
        s = datetime.strptime(start, '%Y-%m-%d'); e = datetime.strptime(end, '%Y-%m-%d'); d = timedelta(days=1)
        curr = s
        while curr <= e:
            if curr.weekday() != 6:
                day_str = curr.strftime('%Y-%m-%d')
                for nv in nvs:
                    cursor.execute("SELECT COUNT(*) FROM PhanCa WHERE MaNV=? AND NgayLamViec=?", (nv, day_str))
                    if cursor.fetchone()[0] == 0: cursor.execute("INSERT INTO PhanCa (MaNV, MaCa, NgayLamViec) VALUES (?,?,?)", (nv, ca, day_str))
            curr += d
        conn.commit(); return True
    except: return False
    finally: conn.close()

def lay_ca_tuong_lai_cua_nv(ma_nv):
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT p.NgayLamViec, c.MaCa, c.TenCa, c.GioBatDau, c.GioKetThuc FROM PhanCa p JOIN CaLamViec c ON p.MaCa = c.MaCa WHERE p.MaNV=? AND p.NgayLamViec > GETDATE() ORDER BY p.NgayLamViec", (ma_nv,))
        res = []
        for r in cursor.fetchall():
            it = dict(zip([c[0] for c in cursor.description], r)); it['NgayHienThi'] = it['NgayLamViec'].strftime('%d/%m/%Y')
            res.append(it)
        return res
    finally: conn.close()

def gui_yeu_cau_thay_doi(ma_nv, loai, ly_do, ngay_cu, ca_cu, ngay_moi=None, ca_moi=None):
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO YeuCau (MaNV, LoaiYeuCau, LyDo, NgayCanNghi, CaCanNghi, NgayMuonDoi, CaMuonDoi, TrangThai, NgayGui, DaDoc) VALUES (?,?,?,?,?,?,?,N'ChoDuyet',GETDATE(),0)", (ma_nv, loai, ly_do, ngay_cu, ca_cu, ngay_moi, ca_moi))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def lay_danh_sach_yeu_cau():
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT y.*, e.HoTen, c1.TenCa as TenCaCu, c2.TenCa as TenCaMoi FROM YeuCau y JOIN Employee e ON y.MaNV = e.MaNV LEFT JOIN CaLamViec c1 ON y.CaCanNghi = c1.MaCa LEFT JOIN CaLamViec c2 ON y.CaMuonDoi = c2.MaCa WHERE y.LoaiYeuCau IN ('XIN_NGHI','DOI_CA') ORDER BY y.NgayGui DESC")
        return [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]
    finally: conn.close()

def duyet_yeu_cau(ma_yc, trang_thai):
    """Duyệt nghỉ phép/đổi ca -> Reset DaDoc=0 để báo cho User"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        # QUAN TRỌNG: Reset DaDoc = 0 để thông báo lại hiện lên chuông của Nhân viên
        cursor.execute("UPDATE YeuCau SET TrangThai=?, DaDoc=0 WHERE MaYC=?", (trang_thai, ma_yc))
        
        if trang_thai == 'DaDuyet':
            cursor.execute("SELECT * FROM YeuCau WHERE MaYC=?", (ma_yc,)); req = cursor.fetchone()
            if req.LoaiYeuCau == 'XIN_NGHI': cursor.execute("DELETE FROM PhanCa WHERE MaNV=? AND NgayLamViec=? AND MaCa=?", (req.MaNV, req.NgayCanNghi, req.CaCanNghi))
            elif req.LoaiYeuCau == 'DOI_CA': cursor.execute("UPDATE PhanCa SET NgayLamViec=?, MaCa=? WHERE MaNV=? AND NgayLamViec=? AND MaCa=?", (req.NgayMuonDoi, req.CaMuonDoi, req.MaNV, req.NgayCanNghi, req.CaCanNghi))
        conn.commit(); return True
    except Exception as e: print(e); return False
    finally: conn.close()

def gui_yeu_cau_ung_luong(ma_nv, so_tien, ly_do, ngay_ung):
    conn = get_db_connection()
    if not conn: return False, "Lỗi DB"
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT LuongCoBan FROM Employee WHERE MaNV=?", (ma_nv,)); luong = cursor.fetchone().LuongCoBan or 0
        if so_tien > float(luong) * 0.5: return False, "Vượt quá 50%"
        cursor.execute("INSERT INTO YeuCau (MaNV, LoaiYeuCau, LyDo, SoTien, NgayCanNghi, TrangThai, NgayGui, DaDoc) VALUES (?, 'UNG_LUONG', ?, ?, ?, N'ChoDuyet', GETDATE(), 0)", (ma_nv, ly_do, so_tien, ngay_ung))
        conn.commit(); return True, "Thành công"
    except Exception as e: return False, str(e)
    finally: conn.close()

def lay_ds_yeu_cau_ung_luong():
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT y.*, e.HoTen FROM YeuCau y JOIN Employee e ON y.MaNV = e.MaNV WHERE y.LoaiYeuCau='UNG_LUONG' AND y.TrangThai=N'ChoDuyet' ORDER BY y.NgayGui DESC")
        res = []
        for r in cursor.fetchall():
            it = dict(zip([c[0] for c in cursor.description], r))
            it['SoTien_Fmt'] = "{:,.0f}".format(it['SoTien'])
            it['ThangNam'] = it['NgayCanNghi'].strftime('%m/%Y') if it['NgayCanNghi'] else ""
            res.append(it)
        return res
    finally: conn.close()

def duyet_ung_luong(ma_yc, trang_thai, admin_id):
    """Duyệt ứng lương -> Reset DaDoc=0 để báo cho User"""
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        # QUAN TRỌNG: Reset DaDoc = 0
        cursor.execute("UPDATE YeuCau SET TrangThai=?, DaDoc=0 WHERE MaYC=?", (trang_thai, ma_yc))
        
        if trang_thai == 'DaDuyet':
            cursor.execute("SELECT MaNV, SoTien, NgayCanNghi FROM YeuCau WHERE MaYC=?", (ma_yc,)); req = cursor.fetchone()
            ma=req.MaNV; tien=req.SoTien; t=req.NgayCanNghi.month; n=req.NgayCanNghi.year
            cursor.execute("SELECT SalaryId, UngLuong FROM Salary WHERE MaNV=? AND Thang=? AND Nam=?", (ma,t,n)); sal=cursor.fetchone()
            if sal:
                new_ung = (sal.UngLuong or 0) + tien
                cursor.execute("UPDATE Salary SET UngLuong=? WHERE SalaryId=?", (new_ung, sal.SalaryId))
                cursor.execute("SELECT LuongCoBan, SoCongChuan, SoCongThucTe, ThuongThem, Phat FROM Salary WHERE SalaryId=?", (sal.SalaryId,)); s = cursor.fetchone()
                lc = (float(s.LuongCoBan)/float(s.SoCongChuan)*float(s.SoCongThucTe)) if s.SoCongChuan and s.SoCongThucTe else 0
                tong = round(lc + float(s.ThuongThem or 0) - float(s.Phat or 0) - float(new_ung))
                cursor.execute("UPDATE Salary SET Tong=? WHERE SalaryId=?", (tong, sal.SalaryId))
            else:
                cursor.execute("INSERT INTO Salary (MaNV,Thang,Nam,LuongCoBan,UngLuong,Tong,TrangThai,NgayTao) VALUES (?,?,?,0,?, ?, N'Chờ duyệt', GETDATE())", (ma,t,n,tien, -tien))
        conn.commit(); return True
    except: return False
    finally: conn.close()

# --- 7. THÔNG BÁO & LOG (AUDIT) ---
def lay_thong_bao_ca_nhan(ma_nv, role_id):
    """
    Lấy danh sách thông báo dựa trên vai trò:
    - Admin: Nhận thông báo khi có yêu cầu mới (Chờ duyệt).
    - Nhân viên: Nhận thông báo khi yêu cầu đã có kết quả (Duyệt/Từ chối).
    """
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        
        if role_id in ['QuanLyCapCao', 'QuanLyCapThap']:
            query = """
            SELECT TOP 10 y.LoaiYeuCau, y.LyDo, y.SoTien, y.NgayCanNghi, y.NgayMuonDoi, 
                          y.TrangThai, y.NgayGui, y.DaDoc, e.HoTen
            FROM YeuCau y
            JOIN Employee e ON y.MaNV = e.MaNV
            WHERE y.TrangThai = N'ChoDuyet'
            ORDER BY y.DaDoc ASC, y.NgayGui DESC
            """
            cursor.execute(query)
        
        else:
            query = """
            SELECT TOP 10 y.LoaiYeuCau, y.LyDo, y.SoTien, y.NgayCanNghi, y.NgayMuonDoi, 
                          y.TrangThai, y.NgayGui, y.DaDoc, e.HoTen
            FROM YeuCau y
            JOIN Employee e ON y.MaNV = e.MaNV
            WHERE y.MaNV = ? 
              AND y.TrangThai IN (N'DaDuyet', N'TuChoi')
            ORDER BY y.DaDoc ASC, y.NgayGui DESC
            """
            cursor.execute(query, (ma_nv,))
            
        columns = [c[0] for c in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            
            txt = ""
            link = "#"
            
            ngay_format = item['NgayCanNghi'].strftime('%d/%m') if item['NgayCanNghi'] else "..."
            
            if role_id in ['QuanLyCapCao', 'QuanLyCapThap']:
                ten = item['HoTen']
                if item['LoaiYeuCau'] == 'UNG_LUONG': 
                    txt = f"{ten} xin ứng {item['SoTien']:,.0f}đ"
                    link = "/admin/quan_ly_luong"
                elif item['LoaiYeuCau'] == 'XIN_NGHI': 
                    txt = f"{ten} xin nghỉ ngày {ngay_format}"
                    link = "/admin/quan_ly_ca"
                elif item['LoaiYeuCau'] == 'DOI_CA': 
                    txt = f"{ten} xin đổi ca ngày {ngay_format}"
                    link = "/admin/quan_ly_ca"
                
                item['Icon'] = 'fa-clock'
                item['Color'] = 'warning text-dark'
                item['TextStatus'] = 'Chờ duyệt'
                
            else:
                if item['LoaiYeuCau'] == 'UNG_LUONG': 
                    txt = f"Yêu cầu ứng {item['SoTien']:,.0f}đ"
                    link = "/employee/salary"
                elif item['LoaiYeuCau'] == 'XIN_NGHI': 
                    txt = f"Đơn xin nghỉ ngày {ngay_format}"
                    link = "/employee/schedule"
                elif item['LoaiYeuCau'] == 'DOI_CA': 
                    txt = f"Đơn đổi ca ngày {ngay_format}"
                    link = "/employee/schedule"
                
                # User thấy kết quả
                if item['TrangThai'] == 'DaDuyet': 
                    item['Icon'] = 'fa-check-circle'; item['Color'] = 'success'; item['TextStatus'] = 'Đã duyệt'
                else: 
                    item['Icon'] = 'fa-times-circle'; item['Color'] = 'danger'; item['TextStatus'] = 'Từ chối'
            
            item['NoiDung'] = txt
            item['Link'] = link
            results.append(item)
        return results
    finally: 
        conn.close()

def danh_dau_da_doc(ma_nv, role_id):
    """
    Đánh dấu đã đọc dựa trên vai trò.
    """
    conn = get_db_connection()
    if not conn: return False
    try:
        cursor = conn.cursor()
        
        if role_id in ['QuanLyCapCao', 'QuanLyCapThap']:
            # Admin đọc -> Update các đơn 'ChoDuyet' thành đã đọc
            # (Nghĩa là Admin đã nhìn thấy thông báo này rồi)
            query = "UPDATE YeuCau SET DaDoc = 1 WHERE TrangThai = N'ChoDuyet' AND (DaDoc = 0 OR DaDoc IS NULL)"
            cursor.execute(query)
        else:
            # User đọc -> Update các đơn của mình đã có kết quả thành đã đọc
            query = "UPDATE YeuCau SET DaDoc = 1 WHERE MaNV = ? AND TrangThai IN (N'DaDuyet', N'TuChoi') AND (DaDoc = 0 OR DaDoc IS NULL)"
            cursor.execute(query, (ma_nv,))
            
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi đánh dấu đọc: {e}")
        return False
    finally:
        conn.close()

def lay_lich_su_chinh_sua(bang_anh_huong=None):
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        query = """
        SELECT a.AuditId, e.HoTen as NguoiSua, a.HanhDong, a.ThoiGian 
        FROM AuditLog a 
        LEFT JOIN Employee e ON a.NguoiSua = CAST(e.MaNV as NVARCHAR)
        """
        params = []
        if bang_anh_huong: 
            query += " WHERE a.BangAnhHuong = ?"
            params.append(bang_anh_huong)
        query += " ORDER BY a.ThoiGian DESC"
        
        cursor.execute(query, tuple(params))
        cols = [c[0] for c in cursor.description]
        results = []
        for row in cursor.fetchall():
            it = dict(zip(cols, row))
            if it['ThoiGian']: 
                it['ThoiGian'] = it['ThoiGian'].strftime('%d/%m/%Y %H:%M')
            results.append(it)
        return results
    finally: conn.close()

# --- ADMIN DASHBOARD ---
def lay_thong_ke_dashboard():
    conn = get_db_connection()
    if not conn: return {'total':0, 'present':0, 'late':0, 'absent':0}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Employee"); total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT MaNV) FROM AttendLog WHERE CAST(CheckIn AS DATE) = CAST(GETDATE() AS DATE)"); present = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM AttendLog WHERE CAST(CheckIn AS DATE) = CAST(GETDATE() AS DATE) AND CAST(CheckIn AS TIME) > '08:00:00'"); late = cursor.fetchone()[0]
        return {'total': total, 'present': present, 'late': late, 'absent': max(0, total - present)}
    finally: conn.close()

def lay_hoat_dong_gan_day():
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 5 a.CheckIn, a.CheckOut, e.HoTen FROM AttendLog a JOIN Employee e ON a.MaNV = e.MaNV WHERE CAST(a.CheckIn AS DATE) = CAST(GETDATE() AS DATE) ORDER BY a.CheckIn DESC")
        cols = [c[0] for c in cursor.description]
        res = []
        for row in cursor.fetchall():
            it = dict(zip(cols, row))
            if it['CheckOut']: it.update({'Time': it['CheckOut'].strftime('%H:%M'), 'Type': 'Check-out', 'Status': 'Hoàn thành', 'Color': 'primary'})
            else:
                it.update({'Time': it['CheckIn'].strftime('%H:%M'), 'Type': 'Check-in'})
                if it['CheckIn'].time() > datetime.strptime('08:00:00', '%H:%M:%S').time(): it.update({'Status': 'Đi muộn', 'Color': 'warning text-dark'})
                else: it.update({'Status': 'Đúng giờ', 'Color': 'success'})
            res.append(it)
        return res
    finally: conn.close()