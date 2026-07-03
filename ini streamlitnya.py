"""
WebMon Downloader - Login + Filter + Detail
"""

import streamlit as st
import requests
import zipfile
import tempfile
import io
import jwt
import pandas as pd
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="WebMon Downloader",
    page_icon="📥",
    layout="wide"
)

# ============================================================================
# CONFIGURATION
# ============================================================================

API_BASE_URL = "https://api2.karantinaindonesia.go.id/webmon-be"
CERT_BASE_URL = "https://cert.karantinaindonesia.go.id"
TIMEOUT = 30

# ============================================================================
# SESSION STATE
# ============================================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.token = None
    st.session_state.user_info = None
    st.session_state.documents = []

# ============================================================================
# AUTH MANAGER
# ============================================================================

class AuthManager:
    """Mengelola authentikasi ke WebMon API."""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: Optional[str] = None
        self.user_info: Optional[Dict[str, Any]] = None
    
    def login(self, username: str, password: str) -> bool:
        """Login ke WebMon API."""
        try:
            login_url = f"{self.base_url}/api/auth/login"
            payload = {
                "username": username,
                "password": password
            }
            
            response = requests.post(
                login_url,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                
                if not self.token:
                    return False
                
                # Parse JWT
                try:
                    decoded = jwt.decode(
                        self.token,
                        options={"verify_signature": False}
                    )
                    self.user_info = {
                        "nama": decoded.get("nama", "N/A"),
                        "upt": decoded.get("upt", "N/A"),
                        "username": decoded.get("username", "N/A"),
                        "email": decoded.get("email", "N/A"),
                        "role": decoded.get("role", "N/A"),
                    }
                except Exception:
                    pass
                
                return True
            else:
                return False
        
        except Exception as e:
            st.error(f"❌ Login error: {str(e)}")
            return False
    
    def get_token(self) -> Optional[str]:
        return self.token
    
    def get_auth_header(self) -> Dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}


# ============================================================================
# WEBMON API
# ============================================================================

class WebMonAPI:
    """API untuk WebMon."""
    
    def __init__(self, base_url: str, auth_header: Dict[str, str], timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header
        self.timeout = timeout
    
    def fetch_pelepasan(
        self,
        upt: Optional[str] = None,
        lingkup: Optional[str] = None,
        karantina: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch dokumen Pelepasan dari WebMon API."""
        try:
            # Build payload dengan form-urlencoded
            payload = {}
            
            if upt:
                payload["upt"] = upt
            if lingkup:
                payload["lingkup"] = lingkup
            if karantina:
                payload["karantina"] = karantina
            if start_date:
                payload["start_date"] = start_date
            if end_date:
                payload["end_date"] = end_date
            
            url = f"{self.base_url}/api/pelepasan"
            
            # PENTING: Gunakan POST dengan data (form-urlencoded)
            response = requests.post(
                url,
                data=payload,
                headers=self.auth_header,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            else:
                error_msg = response.json().get("message", f"Status {response.status_code}")
                st.error(f"❌ Fetch gagal: {error_msg}")
                return []
        
        except Exception as e:
            st.error(f"❌ Fetch error: {str(e)}")
            return []
    
    def get_document_detail(self, doc_id: str, modul: str = "perlakuan") -> Optional[Dict[str, Any]]:
        """Fetch detail dokumen untuk dapat link sertifikat."""
        try:
            payload = {
                "id": doc_id,
                "modul": modul
            }
            
            url = f"{self.base_url}/detail/view"
            
            response = requests.post(
                url,
                data=payload,
                headers=self.auth_header,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
        
        except Exception:
            return None
    
    def get_download_link(self, doc_id: str) -> Optional[str]:
        """Ambil link sertifikat dari detail dokumen."""
        try:
            detail = self.get_document_detail(doc_id)
            
            if not detail or not detail.get("data"):
                return None
            
            detail_data = detail.get("data", {})
            timeline = detail_data.get("timeline", [])
            
            # Cari link dengan print_cert
            for item in timeline:
                link = item.get("link")
                if link and "print_cert" in link:
                    return link
            
            return None
        
        except Exception:
            return None
        
    def get_all_download_links(self, doc_id: str) -> List[Dict[str, str]]:
        """Ambil semua link dokumen dari timeline."""
        try:
            detail = self.get_document_detail(doc_id)
            
            if not detail or not detail.get("data"):
                return []
            
            detail_data = detail.get("data", {})
            timeline = detail_data.get("timeline", [])
            
            links = []
            for item in timeline:
                link = item.get("link")
                judul = item.get("judul", "Dokumen")
                
                if link and "print_cert" in link:
                    links.append({
                        "judul": judul,
                        "link": link,
                        "kode": item.get("kode", "")
                    })
            
            return links
        
        except Exception:
            return []

# ============================================================================
# MAIN UI
# ============================================================================

st.title("📥 WebMon Downloader")

# ============================================================================
# SIDEBAR LOGIN
# ============================================================================

with st.sidebar:
    st.title("🔐 Login")
    st.markdown("---")
    
    if not st.session_state.authenticated:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            submitted = st.form_submit_button("🔐 Login", use_container_width=True, type="primary")
            
            if submitted:
                if username and password:
                    auth_manager = AuthManager(API_BASE_URL, timeout=TIMEOUT)
                    
                    with st.spinner("🔄 Logging in..."):
                        if auth_manager.login(username, password):
                            st.session_state.authenticated = True
                            st.session_state.token = auth_manager.get_token()
                            st.session_state.user_info = auth_manager.user_info
                            st.success("✅ Login berhasil!")
                            st.rerun()
                        else:
                            st.error("❌ Login gagal!")
                else:
                    st.error("Username dan password harus diisi!")
    
    else:
        st.success("✅ Logged In")
        
        if st.session_state.user_info:
            st.write(f"👤 **{st.session_state.user_info.get('nama')}**")
            st.write(f"🏢 {st.session_state.user_info.get('upt')}")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.token = None
            st.session_state.user_info = None
            st.session_state.documents = []
            st.rerun()

# ============================================================================
# MAIN CONTENT
# ============================================================================

if not st.session_state.authenticated:
    st.info("👈 Silakan login di sidebar")
else:
    st.subheader("📄 Dokumen Pelepasan")
    st.markdown("---")
    st.subheader("🔍 Filter Dokumen")
       
    # Filter Row 1
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        upt = st.text_input("UPT (contoh: 1400)", value="")
    
    with col2:
        lingkup_options = {
            "EX": "Ekspor",
            "IM": "Impor",
            "DK": "Domestik Keluar",
            "DM": "Domestik Masuk"
        }
        lingkup = st.selectbox(
            "Lingkup",
            [""] + list(lingkup_options.keys()),
            format_func=lambda x: lingkup_options.get(x, x) if x else "Semua"
        )
    
    with col3:
        karantina_options = {
            "T": "Tumbuhan",
            "H": "Hewan",
            "I": "Ikan"
        }
        karantina = st.selectbox(
            "Karantina",
            [""] + list(karantina_options.keys()),
            format_func=lambda x: karantina_options.get(x, x) if x else "Semua"
        )
    
    with col4:
        satpel = st.text_input("Satpel (opsional)", value="")
        
    # Filter Row 2 - Date Range
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input(
            "Tanggal Awal",
            value=datetime.now() - timedelta(days=7)
        )
    
    with col2:
        end_date = st.date_input(
            "Tanggal Akhir",
            value=datetime.now()
        )
    
    st.markdown("---")
    
    # Search Button
    col1, col2 = st.columns([1, 4])
    
    with col1:
        search_button = st.button(
            "🔄 Cari",
            use_container_width=True,
            type="primary"
        )
    
    with col2:
        st.write("")
    
         # Execute search
    if search_button:
        with st.spinner("⏳ Mencari dokumen..."):
            api = WebMonAPI(
                API_BASE_URL,
                {"Authorization": f"Bearer {st.session_state.token}"},
                timeout=TIMEOUT
            )
            
            documents = api.fetch_pelepasan(
                upt=upt if upt else None,
                lingkup=lingkup if lingkup else None,
                karantina=karantina if karantina else None,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            # Filter berdasarkan Satpel jika diisi
            if satpel:
                documents = [d for d in documents if satpel.lower() in d.get("satpel", "").lower()]
            
            st.session_state.documents = documents
            
            if documents:
                st.success(f"✅ Ditemukan {len(documents)} dokumen!")
            else:
                st.warning("⚠️ Tidak ada dokumen yang sesuai filter")

    # Show Results
    if st.session_state.documents:
        st.markdown("---")
        st.subheader(f"📋 Hasil ({len(st.session_state.documents)} dokumen)")
        
        # Filter Satpel di hasil
        unique_satpels = sorted(set(d.get("satpel", "") for d in st.session_state.documents if d.get("satpel")))
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.write("")
        
        with col2:
            selected_satpels = st.multiselect(
                "Filter Satpel",
                unique_satpels,
                default=unique_satpels
            )
        
        # Filter dokumen berdasarkan Satpel yang dipilih
        filtered_documents = [d for d in st.session_state.documents if d.get("satpel") in selected_satpels]
        
        # Create dataframe
        df_data = []
        docs_with_links = []  # Simpan dokumen dengan linknya
        
        # Initialize API
        api = WebMonAPI(
            API_BASE_URL,
            {"Authorization": f"Bearer {st.session_state.token}"},
            timeout=TIMEOUT
        )
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with ThreadPoolExecutor(max_workers=10) as executor:

            futures = {
                executor.submit(api.get_all_download_links, doc.get("id", "")): doc
                for doc in filtered_documents
            }
        
            completed = 0
        
            for future in as_completed(futures):
        
                completed += 1
        
                progress_bar.progress(completed / len(filtered_documents))
                status_text.text(
                    f"⏳ Fetch detail {completed}/{len(filtered_documents)}"
                )
        
                doc = futures[future]
                links = future.result()
        
                df_data.append({
                    "No": completed,
                    "No. Aju": doc.get("no_aju", "N/A"),
                    "Pemohon": doc.get("nama_pemohon", "N/A")[:40],
                    "Satpel": doc.get("satpel", "N/A")[:25],
                    "Komoditas": doc.get("komoditas", "N/A")[:30],
                    "File PDF": f"📄 {len(links)}" if links else "❌ 0"
                })
        
                if links:
                    docs_with_links.append({
                        "no_aju": doc.get("no_aju"),
                        "nama_pemohon": doc.get("nama_pemohon"),
                        "links": links
                    })
        
        progress_bar.empty()
        status_text.empty()
        
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Summary
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📊 Dokumen Ditampilkan", len(filtered_documents))
        
        with col2:
            st.metric("👤 Pemohon Unik", len(set(d.get("nama_pemohon", "") for d in filtered_documents)))
        
        with col3:
            total_files = sum(len(d["links"]) for d in docs_with_links)
            st.metric("📄 Total File PDF", total_files)
        
        # List semua file PDF
        st.markdown("---")
        st.subheader("📄 Daftar File PDF")
        
        for doc_info in docs_with_links:
            with st.expander(f"📋 {doc_info['no_aju']} - {doc_info['nama_pemohon'][:40]}"):
                for link_info in doc_info["links"]:
                    st.write(f"📄 **{link_info['judul']}** ({link_info['kode']})")
                    st.write(f"🔗 Link tersedia")

                # Download Section
        st.markdown("---")
        st.subheader("⬇️ Download Sertifikat")
               
        if st.button("⬇️ Download Semua File PDF", use_container_width=True, type="primary"):
            import os
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def download_file(link, filepath, token):
                """Download single file."""
                try:
                    response = requests.get(
                        link,
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=TIMEOUT,
                        stream=True
                    )
                    
                    if response.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        return True, None
                    return False, f"Status {response.status_code}"
                except Exception as e:
                    return False, str(e)
            
            import tempfile

            temp_dir = tempfile.TemporaryDirectory()
            final_download_path = temp_dir.name
                           
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            success_count = 0
            failed_count = 0
            total_files = 0
            
            # Hitung total file
            for doc_info in docs_with_links:
                total_files += len(doc_info["links"])
            
            # Siapkan list download tasks
            download_tasks = []
            
            for doc_info in docs_with_links:
                no_aju = doc_info["no_aju"]
                folder_aju = os.path.join(final_download_path, no_aju)
                try:
                    os.makedirs(folder_aju, exist_ok=True)
                except:
                    continue
                
                for link_info in doc_info["links"]:
                    judul = link_info["judul"]
                    kode = link_info["kode"]
                    link = link_info["link"]
                    
                    filename = f"{kode}_{judul[:20]}.pdf"
                    filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                    filepath = os.path.join(folder_aju, filename)
                    
                    download_tasks.append({
                        "link": link,
                        "filepath": filepath,
                        "judul": judul,
                        "no_aju": no_aju
                    })
            
            # Download dengan parallel (5 thread sekaligus)
            with ThreadPoolExecutor(max_workers=15) as executor:
                futures = {}
                
                for task in download_tasks:
                    future = executor.submit(
                        download_file,
                        task["link"],
                        task["filepath"],
                        st.session_state.token
                    )
                    futures[future] = task
                
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    progress = completed / total_files
                    progress_bar.progress(progress)
                    
                    task = futures[future]
                    status_text.text(f"⏳ Download {completed}/{total_files}: {task['judul']}")
                    
                    success, error = future.result()
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
            
            progress_bar.empty()
            status_text.empty()
            
            # Result
            st.markdown("---")
            st.subheader("📊 Hasil Download")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("✅ Sukses", success_count)
            
            with col2:
                st.metric("❌ Gagal", failed_count)
            
            with col3:
                percentage = (success_count / total_files * 100) if total_files > 0 else 0
                st.metric("📊 Success Rate", f"{percentage:.1f}%")
            
            st.info(f"📁 File disimpan di: `{os.path.abspath(final_download_path)}`")
            
            if success_count > 0:
                st.success(f"✅ {success_count} file berhasil diunduh!")
                import io
                import zipfile
                
                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                
                    for root, dirs, files in os.walk(final_download_path):
                
                        for file in files:
                
                            filepath = os.path.join(root, file)
                
                            arcname = os.path.relpath(filepath, final_download_path)
                
                            zipf.write(filepath, arcname)
                
                zip_buffer.seek(0)
                st.download_button(
                    "📦 Download ZIP",
                    data=zip_buffer,
                    file_name="WebMon_Sertifikat.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                temp_dir.cleanup()
            if failed_count > 0:
                st.warning(f"⚠️ {failed_count} file gagal diunduh!")
                if st.button("⬇️ Download Semua File PDF", use_container_width=True, type="primary"):
                    import os
                    
                    # Buat folder utama jika belum ada
                    try:
                        os.makedirs(final_download_path, exist_ok=True)
                    except Exception as e:
                        st.error(f"❌ Gagal membuat folder: {str(e)}")
                        st.stop()
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    success_count = 0
                    failed_count = 0
                    total_files = 0
                    
                    # Hitung total file yang akan didownload
                    for doc_info in docs_with_links:
                        total_files += len(doc_info["links"])
                    
                    current_file = 0
                    
                    # Download semua file dari semua dokumen
                    for doc_info in docs_with_links:
                        no_aju = doc_info["no_aju"]
                        nama_pemohon = doc_info["nama_pemohon"]
                        
                        # Buat folder per No. Aju
                        folder_aju = os.path.join(final_download_path, no_aju)
                        try:
                            os.makedirs(folder_aju, exist_ok=True)
                        except Exception as e:
                            st.error(f"❌ Gagal membuat folder {no_aju}: {str(e)}")
                            continue
                        
                        for link_info in doc_info["links"]:
                            current_file += 1
                            progress = current_file / total_files if total_files > 0 else 0
                            progress_bar.progress(progress)
                            
                            judul = link_info["judul"]
                            kode = link_info["kode"]
                            link = link_info["link"]
                            
                            status_text.text(f"⏳ Download {current_file}/{total_files}: {no_aju} - {judul}")
                            
                            # Download file
                            try:
                                response = requests.get(
                                    link,
                                    headers={"Authorization": f"Bearer {st.session_state.token}"},
                                    timeout=TIMEOUT,
                                    stream=True
                                )
                                
                                if response.status_code == 200:
                                    # Buat nama file
                                    filename = f"{kode}_{judul[:20]}.pdf"
                                    # Bersihkan invalid characters
                                    filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                                    
                                    filepath = os.path.join(folder_aju, filename)
                                    
                                    # Simpan file
                                    with open(filepath, 'wb') as f:
                                        for chunk in response.iter_content(chunk_size=65536):
                                            if chunk:
                                                f.write(chunk)
                                    
                                    success_count += 1
                                else:
                                    failed_count += 1
                            
                            except Exception as e:
                                failed_count += 1
                    
                    progress_bar.empty()
                    status_text.empty()
                    
                    # Result
                    st.markdown("---")
                    st.subheader("📊 Hasil Download")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("✅ Sukses", success_count)
                    
                    with col2:
                        st.metric("❌ Gagal", failed_count)
                    
                    with col3:
                        percentage = (success_count / total_files * 100) if total_files > 0 else 0
                        st.metric("📊 Success Rate", f"{percentage:.1f}%")
                    
                    st.info(f"📁 File disimpan di: `{os.path.abspath(final_download_path)}`")
                    
                    if success_count > 0:
                        st.success(f"✅ {success_count} file berhasil diunduh!")
                    
                    if failed_count > 0:
                        st.warning(f"⚠️ {failed_count} file gagal diunduh!")
