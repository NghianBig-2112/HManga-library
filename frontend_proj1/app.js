/**
 * HManga Library — Core Frontend JavaScript (app.js)
 * ====================================================
 * 1. API_BASE: Tự động cấu hình URL Backend API.
 * 2. showToast: Thông báo nổi (Toast).
 * 3. showConfirmModal: Modal xác nhận thay thế window.confirm().
 * 4. api: Module gọi RESTful API.
 * 5. handleImageFallback: Tự động thử các định dạng ảnh khi 404.
 * 6. renderComicCard: Render HTML thẻ truyện dùng chung.
 * 7. handleDeleteComicCard: Xóa truyện từ thẻ card (dùng chung).
 */

// ==================== CẤU HÌNH API BASE ====================
const API_BASE = window.location.port === '8000' || window.location.port === '3000' 
    ? `${window.location.protocol}//${window.location.hostname}:8000` 
    : 'http://localhost:8000';

// ==================== 1. TOAST NOTIFICATION ====================
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const badgeText = type === 'success' ? 'THÀNH CÔNG' : type === 'error' ? 'LỖI' : type === 'warning' ? 'CẢNH BÁO' : 'THÔNG BÁO';
    toast.innerHTML = `<span class="toast-badge">${badgeText}</span> <span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// ==================== 2. CONFIRM MODAL ====================
function showConfirmModal({
    title = 'Xác nhận',
    message = 'Bạn có chắc chắn muốn thực hiện thao tác này không?',
    confirmText = 'Xác nhận',
    cancelText = 'Hủy',
    type = 'danger',
    onConfirm
}) {
    let modalEl = document.getElementById('global-confirm-modal');
    if (!modalEl) {
        modalEl = document.createElement('div');
        modalEl.id = 'global-confirm-modal';
        modalEl.className = 'modal-overlay';
        document.body.appendChild(modalEl);
    }

    const btnClass = type === 'danger' ? 'btn-danger' : 'btn-primary';
    const borderAccent = type === 'danger' ? 'var(--danger)' : 'var(--primary)';

    modalEl.innerHTML = `
        <div class="modal-card" style="max-width: 440px; text-align: left;">
            <div class="modal-header" style="margin-bottom: 14px;">
                <h3 class="modal-title" style="font-size: 17px; display: flex; align-items: center; gap: 8px;">
                    ${title}
                </h3>
                <button type="button" class="modal-close" id="btn-global-modal-close">&times;</button>
            </div>
            <div style="color: var(--text-muted); font-size: 14px; line-height: 1.6; margin-bottom: 22px; background: rgba(0, 0, 0, 0.35); padding: 14px; border-radius: 8px; border-left: 4px solid ${borderAccent};">
                ${message}
            </div>
            <div class="modal-actions" style="margin-top: 0; justify-content: flex-end; gap: 10px;">
                <button type="button" class="btn btn-secondary" id="btn-global-modal-cancel">${cancelText}</button>
                <button type="button" class="btn ${btnClass}" id="btn-global-modal-confirm">${confirmText}</button>
            </div>
        </div>
    `;

    modalEl.classList.add('active');

    const closeModal = () => {
        modalEl.classList.remove('active');
        document.removeEventListener('keydown', handleKey);
    };

    const handleKey = (e) => {
        if (e.key === 'Escape') closeModal();
    };
    document.addEventListener('keydown', handleKey);

    document.getElementById('btn-global-modal-close').onclick = closeModal;
    document.getElementById('btn-global-modal-cancel').onclick = closeModal;
    
    modalEl.onclick = (e) => {
        if (e.target === modalEl) closeModal();
    };

    const confirmBtn = document.getElementById('btn-global-modal-confirm');
    confirmBtn.onclick = async () => {
        confirmBtn.disabled = true;
        const originalHtml = confirmBtn.innerHTML;
        confirmBtn.innerHTML = 'Đang xử lý...';
        try {
            if (onConfirm) await onConfirm();
            closeModal();
        } catch (err) {
            showToast(err.message || 'Đã xảy ra lỗi!', 'error');
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = originalHtml;
        }
    };
}

// ==================== 3. API CLIENT ====================
const api = {
    // --- COMICS ---
    async getComics(params = {}) {
        const query = new URLSearchParams();
        if (params.folder_id) query.set('folder_id', params.folder_id);
        if (params.author_id) query.set('author_id', params.author_id);
        if (params.q) query.set('q', params.q);
        const res = await fetch(`${API_BASE}/api/comics${query.toString() ? '?' + query.toString() : ''}`);
        if (!res.ok) throw new Error('Không thể tải danh sách truyện');
        return res.json();
    },

    async getDiscoverFilters() {
        const res = await fetch(`${API_BASE}/api/discover/filters`);
        if (!res.ok) throw new Error('Không thể tải bộ lọc khám phá');
        return res.json();
    },

    async getComic(id) {
        const res = await fetch(`${API_BASE}/api/comics/${id}`);
        if (!res.ok) throw new Error('Không tìm thấy truyện');
        return res.json();
    },

    async previewComicById(galleryId) {
        const res = await fetch(`${API_BASE}/api/comics/preview/${galleryId}`);
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Không tìm thấy truyện với ID này trên NHentai!');
        }
        return res.json();
    },

    async addComicById(galleryId, options = {}) {
        const body = {
            gallery_id: parseInt(galleryId, 10)
        };
        if (options && options.folder_id) body.folder_id = parseInt(options.folder_id, 10);
        if (options && options.pages_per_chapter) body.pages_per_chapter = parseInt(options.pages_per_chapter, 10);

        const res = await fetch(`${API_BASE}/api/comics/add-by-id`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Lỗi khi thêm truyện bằng ID');
        }
        return res.json();
    },

    async deleteComic(id) {
        const res = await fetch(`${API_BASE}/api/comics/${id}`, { method: 'DELETE' });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Lỗi khi xóa truyện');
        }
        return res.json();
    },

    // --- CHAPTERS ---
    async addChapterById(comicId, data) {
        const res = await fetch(`${API_BASE}/api/comics/${comicId}/chapters/add-by-id`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Lỗi khi thêm chapter bằng ID');
        }
        return res.json();
    },

    async addChapterInternal(comicId, data) {
        const res = await fetch(`${API_BASE}/api/comics/${comicId}/chapters`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Lỗi khi thêm chapter');
        }
        return res.json();
    },

    async updateChapter(chapterId, data) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Lỗi khi cập nhật chapter');
        }
        return res.json();
    },

    async deleteChapter(chapterId) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}`, { method: 'DELETE' });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Lỗi khi xóa chapter');
        }
        return res.json();
    },

    async getChapter(chapterId) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}`);
        if (!res.ok) throw new Error('Không tìm thấy chapter');
        return res.json();
    },

    async getChapterPages(chapterId) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}/pages`);
        if (!res.ok) throw new Error('Không thể tải các trang của chapter');
        return res.json();
    },

    // --- COVERS (ZERO-STORAGE IN-MEMORY PROXY) ---
    getCoverUrl(filename, galleryId) {
        if (galleryId) {
            return `/api/nhentai/image-proxy?url=${encodeURIComponent(`https://t3.nhentai.net/galleries/${galleryId}/thumb.webp`)}`;
        }
        if (!filename) return 'assets/rem.jpg';
        if (filename.startsWith('http') || filename.startsWith('/api/')) return filename;
        return `assets/${filename}`;
    },

    // --- SEARCH ---
    async searchComics(params = {}) {
        const query = new URLSearchParams();
        if (params.q) query.set('q', params.q);
        if (params.genre) {
            query.set('genre', Array.isArray(params.genre) ? params.genre.join(',') : params.genre);
        }
        if (params.author) query.set('author', params.author);
        if (params.folder_id) query.set('folder_id', params.folder_id);
        const res = await fetch(`${API_BASE}/api/search?${query.toString()}`);
        if (!res.ok) throw new Error('Tìm kiếm thất bại');
        return res.json();
    },

    // --- GENRES ---
    async getGenres() {
        const res = await fetch(`${API_BASE}/api/genres`);
        if (!res.ok) throw new Error('Không thể tải danh sách thể loại');
        return res.json();
    },

    // --- AUTHORS ---
    async getAuthors() {
        const res = await fetch(`${API_BASE}/api/authors`);
        if (!res.ok) throw new Error('Không thể tải danh sách tác giả');
        return res.json();
    },

    // --- NHENTAI ONLINE EXPLORE & READ ---
    async getNhentaiExplore(params = {}) {
        const query = new URLSearchParams();
        if (params.page) query.set('page', params.page);
        if (params.sort) query.set('sort', params.sort);
        if (params.q) query.set('q', params.q);
        const res = await fetch(`${API_BASE}/api/nhentai/explore?${query.toString()}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể tải danh sách từ NHentai');
        }
        return res.json();
    },

    async getNhentaiGalleryPages(galleryId) {
        const res = await fetch(`${API_BASE}/api/nhentai/gallery/${galleryId}/pages`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể tải thông tin đọc online');
        }
        return res.json();
    },

    // --- FOLDERS (SPOTIFY-STYLE) ---
    async getFolders() {
        const res = await fetch(`${API_BASE}/api/folders`);
        if (!res.ok) throw new Error('Không thể tải danh sách thư mục');
        return res.json();
    },

    async createFolder(data) {
        const res = await fetch(`${API_BASE}/api/folders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể tạo thư mục');
        }
        return res.json();
    },

    async updateFolder(folderId, data) {
        const res = await fetch(`${API_BASE}/api/folders/${folderId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể cập nhật thư mục');
        }
        return res.json();
    },

    async deleteFolder(folderId) {
        const res = await fetch(`${API_BASE}/api/folders/${folderId}`, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể xóa thư mục');
        }
        return res.json();
    },

    async addComicToFolder(folderId, comicId) {
        const res = await fetch(`${API_BASE}/api/folders/${folderId}/comics`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ comic_id: comicId })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể thêm truyện vào thư mục');
        }
        return res.json();
    },

    async removeComicFromFolder(folderId, comicId) {
        const res = await fetch(`${API_BASE}/api/folders/${folderId}/comics/${comicId}`, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể gỡ truyện khỏi thư mục');
        }
        return res.json();
    },

    // --- SMART CHAPTER SEGMENTATION ---
    async splitComicChapters(comicId, pagesPerChapter) {
        const res = await fetch(`${API_BASE}/api/comics/${comicId}/split-chapters`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pages_per_chapter: pagesPerChapter })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể chia chapter');
        }
        return res.json();
    },

    // --- FAVORITES (NHENTAI TWO-WAY) ---
    async getFavorites(params = {}) {
        const query = new URLSearchParams();
        if (params.page) query.set('page', params.page);
        if (params.q) query.set('q', params.q);
        const res = await fetch(`${API_BASE}/api/nhentai/favorites?${query.toString()}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể tải danh sách Favorites (Yêu cầu API Key)');
        }
        return res.json();
    },

    async addFavorite(galleryId) {
        const res = await fetch(`${API_BASE}/api/nhentai/gallery/${galleryId}/favorite`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể thêm vào Favorites (Yêu cầu API Key)');
        }
        return res.json();
    },

    async removeFavorite(galleryId) {
        const res = await fetch(`${API_BASE}/api/nhentai/gallery/${galleryId}/favorite`, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể gỡ khỏi Favorites (Yêu cầu API Key)');
        }
        return res.json();
    },

    async checkFavorite(galleryId) {
        const res = await fetch(`${API_BASE}/api/nhentai/gallery/${galleryId}/favorite`);
        if (!res.ok) return { is_favorite: false };
        return res.json();
    },

    async saveFromFavorite(data) {
        const res = await fetch(`${API_BASE}/api/comics/save-from-favorite`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Không thể lưu truyện vào thư viện');
        }
        return res.json();
    },

    async getNhentaiStatus() {
        const res = await fetch(`${API_BASE}/api/nhentai/status`);
        if (!res.ok) return { configured: false, valid: false };
        return res.json();
    }
};

// ==================== 4. IMAGE FALLBACK ====================
function handleImageFallback(img, onFinalFail) {
    if (!img || !img.src) return;
    if (img.src.includes('rem.jpg')) return;

    // Nếu là URL proxy nội bộ gặp lỗi, chuyển ngay về ảnh mặc định Rem
    if (img.src.includes('/api/nhentai/image-proxy')) {
        img.onerror = null;
        img.src = 'assets/rem.jpg';
        if (typeof onFinalFail === 'function') onFinalFail(img);
        return;
    }
    
    const candidateExts = ['webp', 'jpg', 'png', 'jpeg'];
    let tried = (img.dataset.triedExts || '').split(',').filter(Boolean);
    
    const currentUrl = img.src;
    const match = currentUrl.match(/\.([a-zA-Z0-9]+)(\?.*)?$/);
    if (!match) {
        img.onerror = null;
        img.src = 'assets/rem.jpg';
        if (typeof onFinalFail === 'function') onFinalFail(img);
        return;
    }
    
    const currentExt = match[1].toLowerCase();
    if (!tried.includes(currentExt)) tried.push(currentExt);
    
    const nextExt = candidateExts.find(ext => !tried.includes(ext));
    if (nextExt) {
        tried.push(nextExt);
        img.dataset.triedExts = tried.join(',');
        img.src = currentUrl.replace(/\.([a-zA-Z0-9]+)(\?.*)?$/, `.${nextExt}$2`);
    } else {
        img.onerror = null;
        img.src = 'assets/rem.jpg';
        img.style.maxHeight = '300px';
        if (typeof onFinalFail === 'function') onFinalFail(img);
    }
}

// ==================== 5. RENDER COMIC CARD ====================
function renderComicCard(comic) {
    const coverUrl = comic.cover_url || api.getCoverUrl(comic.cover_filename, comic.gallery_id);
    const genresHtml = (comic.genres || []).slice(0, 3).map(g =>
        `<span class="tag-chip">${g}</span>`
    ).join('') + ((comic.genres && comic.genres.length > 3) ? `<span class="tag-chip">+${comic.genres.length - 3}</span>` : '');
    const titleAttr = (comic.title || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const folderBadges = (comic.folders || []).slice(0, 2).map(f =>
        `<span class="badge text-bg-secondary" style="font-size: 10px; font-weight: 500; opacity: 0.9;"><i class="bi bi-folder2 me-1"></i>${f}</span>`
    ).join(' ');

    return `
        <div class="comic-card" onclick="window.location.href='detail.html?id=${comic.id}'" style="cursor: pointer;">
            <div class="card-thumb-wrapper">
                ${comic.gallery_id ? `<span class="card-id-badge">#${comic.gallery_id}</span>` : ''}
                <button type="button" class="btn-card-delete" data-comic-id="${comic.id}" data-title="${titleAttr}" onclick="handleDeleteComicCard(event)" title="Xóa bộ truyện này">
                    <i class="bi bi-trash3"></i> Xóa
                </button>
                <img src="${coverUrl}" alt="${titleAttr}" class="card-thumb" referrerpolicy="no-referrer" onerror="this.src='assets/rem.jpg'">
            </div>
            <div class="card-body">
                <div class="card-title" title="${titleAttr}">${comic.title}</div>
                <div class="card-author">${comic.author || 'Chưa rõ tác giả'}</div>
                ${folderBadges ? `<div class="d-flex gap-1 flex-wrap mb-1">${folderBadges}</div>` : ''}
                <div class="card-tags">${genresHtml}</div>
            </div>
        </div>
    `;
}

// ==================== 6. DELETE COMIC FROM CARD ====================
/**
 * Xóa truyện từ thẻ card — hàm dùng chung cho tất cả các trang.
 * Mỗi trang cần định nghĩa hàm loadComics() hoặc tương đương để refresh danh sách.
 */
function handleDeleteComicCard(event) {
    event.stopPropagation();
    event.preventDefault();
    const btn = event.currentTarget;
    const comicId = parseInt(btn.dataset.comicId, 10);
    const title = btn.dataset.title || 'bộ truyện này';
    showConfirmModal({
        title: 'Xác nhận xóa truyện',
        message: `Bạn có chắc chắn muốn xóa bộ truyện <b>"${title}"</b> khỏi thư viện không?<br>Hành động này không thể hoàn tác!`,
        confirmText: 'Xóa vĩnh viễn',
        cancelText: 'Hủy bỏ',
        type: 'danger',
        onConfirm: async () => {
            try {
                await api.deleteComic(comicId);
                showToast(`Đã xóa "${title}" thành công!`, 'success');

                // 1. Cập nhật Sidebar thể loại và tác giả (nếu có trên trang)
                if (typeof loadSidebarData === 'function') {
                    await loadSidebarData();
                }

                // 2. Cập nhật lại danh sách truyện (nếu có trên trang)
                if (typeof loadComics === 'function') {
                    await loadComics();
                } else if (typeof doSearch === 'function') {
                    doSearch();
                } else {
                    window.location.reload();
                }
            } catch (err) {
                showToast(err.message || 'Lỗi khi xóa truyện!', 'error');
            }
        }
    });
}
