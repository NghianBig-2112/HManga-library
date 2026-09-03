/**
 * HManga Library — Core Frontend JavaScript Utility (app.js)
 * ==========================================================
 * File tiện ích dùng chung cho toàn bộ giao diện người dùng (Frontend).
 * 
 * Chức năng chính:
 * 1. API_BASE: Tự động cấu hình URL Backend API (port 8000).
 * 2. showToast: Hiển thị thông báo nổi (Toast Notification) báo thành công/thất bại/cảnh báo.
 * 3. api: Module tập trung các hàm gọi RESTful API tới máy chủ (Comics, Chapters, Genres, Authors, Search, Images).
 * 4. URL Parser: Công cụ giải mã URL nhentai (`parseMangaUrl`, `generatePageUrls`, `getPageOneCoverUrl`).
 * 5. Smart Fallback: Tự động thử nhiều định dạng ảnh khi gặp lỗi 404 (`handleImageFallback`).
 * 6. renderComicCard: Render HTML thẻ truyện dùng chung cho nhiều trang.
 * 7. GenreSelectorComponent: Thành phần chọn thể loại dạng nút bấm (Chips) trực quan.
 * 8. AuthorAutocompleteComponent: Thành phần gợi ý và tìm kiếm tác giả thông minh (Autocomplete).
 */

// ==================== CẤU HÌNH API BASE ====================
// Tự động nhận diện URL Backend API dựa theo môi trường chạy của trình duyệt
const API_BASE = window.location.port === '8000' || window.location.port === '3000' 
    ? `${window.location.protocol}//${window.location.hostname}:8000` 
    : 'http://localhost:8000';

// ==================== 1. TOAST NOTIFICATION (THÔNG BÁO NỔI) ====================
/**
 * Hiển thị thông báo dạng Toast nổi ở góc màn hình:
 * @param {string} message - Nội dung thông báo hiển thị cho người dùng
 * @param {'info'|'success'|'error'|'warning'} type - Loại thông báo (success, error, warning, info)
 */
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const badgeText = type === 'success' ? 'SUCCESS' : type === 'error' ? 'ERROR' : type === 'warning' ? 'WARNING' : 'INFO';
    toast.innerHTML = `<span class="toast-badge">${badgeText}</span> <span>${message}</span>`;
    container.appendChild(toast);
    
    // Automatically fade out and remove after 3.5 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// ==================== 1.1 CONFIRM MODAL ====================
/**
 * Modern confirm dialog modal replacing window.confirm
 */
function showConfirmModal({
    title = 'Confirm Action',
    message = 'Are you sure you want to perform this action?',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
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

    const closeBtn = document.getElementById('btn-global-modal-close');
    if (closeBtn) closeBtn.onclick = closeModal;
    const cancelBtn = document.getElementById('btn-global-modal-cancel');
    if (cancelBtn) cancelBtn.onclick = closeModal;
    
    modalEl.onclick = (e) => {
        if (e.target === modalEl) closeModal();
    };

    const confirmBtn = document.getElementById('btn-global-modal-confirm');
    if (confirmBtn) {
        confirmBtn.onclick = async () => {
            confirmBtn.disabled = true;
            const originalHtml = confirmBtn.innerHTML;
            confirmBtn.innerHTML = 'Processing...';
            try {
                if (onConfirm) {
                    await onConfirm();
                }
                closeModal();
            } catch (err) {
                showToast(err.message || 'An error occurred!', 'error');
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = originalHtml;
            }
        };
    }
}

// ==================== 2. API CLIENT (MODULE GỌI BACKEND) ====================
/**
 * Đối tượng trung tâm chứa tất cả các phương thức gọi API tới Backend FastAPI
 */
const api = {
    // ------------------- TRUYỆN TRANH (COMICS) -------------------
    /**
     * Lấy danh sách tất cả các bộ truyện:
     * @param {Object} params - { genre: 'Action', q: 'tên truyện' }
     */
    async getComics(params = {}) {
        const query = new URLSearchParams();
        if (params.genre) query.set('genre', params.genre);
        if (params.q) query.set('q', params.q);
        const res = await fetch(`${API_BASE}/api/comics${query.toString() ? '?' + query.toString() : ''}`);
        if (!res.ok) throw new Error('Failed to load comics list');
        return res.json();
    },

    /**
     * Get comic detail by ID (including chapters and genres)
     */
    async getComic(id) {
        const res = await fetch(`${API_BASE}/api/comics/${id}`);
        if (!res.ok) throw new Error('Comic not found');
        return res.json();
    },

    /**
     * Create a new comic
     */
    async createComic(data) {
        const res = await fetch(`${API_BASE}/api/comics`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Error creating comic');
        return res.json();
    },

    /**
     * Update comic information
     */
    async updateComic(id, data) {
        const res = await fetch(`${API_BASE}/api/comics/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Error updating comic');
        return res.json();
    },

    /**
     * Delete a comic permanently
     */
    async deleteComic(id) {
        const res = await fetch(`${API_BASE}/api/comics/${id}`, { method: 'DELETE' });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Error deleting comic');
        }
        return res.json();
    },

    // ------------------- CHAPTERS -------------------
    /**
     * Create a new chapter
     */
    async createChapter(comicId, data) {
        const res = await fetch(`${API_BASE}/api/comics/${comicId}/chapters`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Error adding chapter');
        }
        return res.json();
    },

    /**
     * Update a chapter
     */
    async updateChapter(chapterId, data) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Error updating chapter');
        }
        return res.json();
    },

    /**
     * Delete a chapter
     */
    async deleteChapter(chapterId) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}`, { method: 'DELETE' });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Error deleting chapter');
        }
        return res.json();
    },

    /**
     * Get a chapter by ID
     */
    async getChapter(chapterId) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}`);
        if (!res.ok) throw new Error('Chapter not found');
        return res.json();
    },

    /**
     * Get page URLs for a chapter
     */
    async getChapterPages(chapterId) {
        const res = await fetch(`${API_BASE}/api/chapters/${chapterId}/pages`);
        if (!res.ok) throw new Error('Failed to load chapter pages');
        return res.json();
    },

    // ------------------- IMAGES & COVERS -------------------
    /**
     * Download cover image to local server
     */
    async downloadCover(url, comicId) {
        const res = await fetch(`${API_BASE}/api/images/download-cover`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, comic_id: comicId })
        });
        if (!res.ok) console.warn('Failed to automatically download cover image');
        return res.json();
    },

    /**
     * Get cover image URL
     */
    getCoverUrl(filename) {
        if (!filename) return 'assets/rem.jpg';
        return `assets/${filename}`;
    },

    // ------------------- SEARCH -------------------
    /**
     * Search comics by query, genre, author
     */
    async searchComics(params = {}) {
        const query = new URLSearchParams();
        if (params.q) query.set('q', params.q);
        if (params.genre) query.set('genre', params.genre);
        if (params.author) query.set('author', params.author);
        const res = await fetch(`${API_BASE}/api/search?${query.toString()}`);
        if (!res.ok) throw new Error('Search failed');
        return res.json();
    },

    /**
     * Check if comic exists by gallery ID
     */
    async checkComicByGalleryId(galleryId) {
        const res = await fetch(`${API_BASE}/api/comics/check/${galleryId}`);
        if (!res.ok) return { exists: false };
        return res.json();
    },

    // ------------------- GENRES -------------------
    /**
     * Get all genres
     */
    async getGenres() {
        const res = await fetch(`${API_BASE}/api/genres`);
        if (!res.ok) throw new Error('Failed to load genres');
        return res.json();
    },

    /**
     * Create a new genre
     */
    async createGenre(name) {
        const res = await fetch(`${API_BASE}/api/genres`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Error adding genre');
        }
        return res.json();
    },

    /**
     * Update genre by ID
     */
    async updateGenre(genreId, name) {
        const res = await fetch(`${API_BASE}/api/genres/${genreId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || 'Error updating genre');
        }
        return res.json();
    },

    async renameGenre(genreId, name) {
        return this.updateGenre(genreId, name);
    },

    /**
     * Delete genre by ID
     */
    async deleteGenre(genreId) {
        const res = await fetch(`${API_BASE}/api/genres/${genreId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Error deleting genre');
        return res.json();
    },

    /**
     * Get comics by genre ID
     */
    async getComicsByGenre(genreId) {
        const res = await fetch(`${API_BASE}/api/genres/${genreId}/comics`);
        if (!res.ok) throw new Error('Failed to load comics by genre');
        return res.json();
    },

    // ------------------- AUTHORS -------------------
    /**
     * Get all authors
     */
    async getAuthors() {
        const res = await fetch(`${API_BASE}/api/authors`);
        if (!res.ok) throw new Error('Failed to load authors');
        return res.json();
    },

    /**
     * Rename author across all comics
     */
    async renameAuthor(oldName, newName) {
        const res = await fetch(`${API_BASE}/api/authors/rename`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_name: oldName, new_name: newName })
        });
        if (!res.ok) throw new Error('Error renaming author');
        return res.json();
    },

    /**
     * Get comics by author name
     */
    async getComicsByAuthor(authorName) {
        const res = await fetch(`${API_BASE}/api/authors/${encodeURIComponent(authorName)}/comics`);
        if (!res.ok) throw new Error('Failed to load comics by author');
        return res.json();
    }
};

// ==================== 3. URL PARSER (BÓC TÁCH LINK NHENTAI) ====================
/**
 * Phân tích cấu trúc đường link ảnh từ nhentai hoặc các nguồn tương thích:
 * Ví dụ: "https://t3.nhentai.net/galleries/4126277/1t.webp"
 * -> prefix: "https://t3.nhentai.net/galleries/4126277/"
 * -> pageNumber: 1
 * -> suffix: "t"
 * -> extension: "webp"
 * -> galleryId: "4126277"
 */
function parseMangaUrl(url) {
    if (!url) return null;
    let cleanUrl = url.trim();
    // Chuẩn hóa trường hợp thumbnail có đuôi kép của NHentai (VD: 2t.jpg.webp -> 2t.webp, 8t.webp.webp -> 8t.webp)
    cleanUrl = cleanUrl.replace(/\.(jpg|jpeg|png|webp)\.webp$/i, '.webp');
    
    const match = cleanUrl.match(/^(.*\/)(\d+)([a-zA-Z]*)\.(\w+)(\?.*)?$/);
    if (!match) return null;

    const prefix = match[1];
    const pageNumber = parseInt(match[2], 10);
    const suffix = match[3] || '';
    const extension = match[4];

    // Hỗ trợ trích xuất cả folder và gallery_id (VD: /001/48410/ -> "001-48410", hoặc /4029076/ -> "4029076")
    const folderGalleryMatch = prefix.match(/\/(\d+)\/(\d+)\/$/);
    let galleryId = '';
    if (folderGalleryMatch) {
        galleryId = `${folderGalleryMatch[1]}-${folderGalleryMatch[2]}`;
    } else {
        const singleMatch = prefix.match(/\/(\d+)\/$/);
        galleryId = singleMatch ? singleMatch[1] : '';
    }

    return { prefix, pageNumber, suffix, extension, galleryId };
}


/**
 * Tự động sinh danh sách toàn bộ URL ảnh từ trang startPage đến endPage:
 * - startPage: Trang bắt đầu (VD: 1, 15, 21...)
 * - endPage: Trang kết thúc (VD: 20, 35, 50...)
 */
function generatePageUrls(baseUrl, startPage = 1, endPage = 1) {
    const s = parseInt(startPage, 10) || 1;
    const e = parseInt(endPage, 10) || s;
    const start = Math.min(s, e);
    const end = Math.max(s, e);
    const total = end - start + 1;

    const parsed = parseMangaUrl(baseUrl);
    if (!parsed) {
        return Array.from({ length: total }, () => baseUrl);
    }
    // Bỏ hậu tố 't' (thumbnail) để người đọc luôn xem ảnh gốc chất lượng cao nhất
    const cleanSuffix = (parsed.suffix && parsed.suffix.toLowerCase() === 't') ? '' : parsed.suffix;
    // NHentai: chuyển domain thumbnail (t/t1-t4) sang domain ảnh gốc (i/i1-i4)
    const cleanPrefix = parsed.prefix.replace(/:\/\/t(\d*)\.nhentai\.net\//g, '://i$1.nhentai.net/');
    return Array.from({ length: total }, (_, i) => {
        const pageNum = start + i;
        return `${cleanPrefix}${pageNum}${cleanSuffix}.${parsed.extension}`;
    });
}


/**
 * Chuyển đổi bất kỳ URL trang nào (VD: .../236t.jpg, .../15.jpg) thành link ảnh bìa trang 1 Full HD (VD: .../1.jpg)
 */
function getPageOneCoverUrl(url, highRes = true) {
    const parsed = parseMangaUrl(url);
    if (!parsed) return url;
    const cleanSuffix = (highRes && parsed.suffix && parsed.suffix.toLowerCase() === 't') ? '' : parsed.suffix;
    // NHentai: chuyển domain thumbnail (t/t1-t4) sang domain ảnh gốc (i/i1-i4)
    let cleanPrefix = parsed.prefix;
    if (highRes) {
        cleanPrefix = cleanPrefix.replace(/:\/\/t(\d*)\.nhentai\.net\//g, '://i$1.nhentai.net/');
    }
    return `${cleanPrefix}1${cleanSuffix}.${parsed.extension}`;
}

/**
 * Smart Fallback: Tự động thử các định dạng ảnh thay thế (.webp ⇄ .jpg ⇄ .png ⇄ .jpeg)
 * khi gặp lỗi 404 do một bộ truyện có nhiều định dạng ảnh xen kẽ.
 * @param {HTMLImageElement} img - Thẻ ảnh xảy ra sự kiện onerror
 * @param {Function} [onFinalFail] - Callback khi đã thử tất cả định dạng nhưng vẫn thất bại
 */
function handleImageFallback(img, onFinalFail) {
    if (!img || !img.src) return;
    
    // Danh sách định dạng thử nghiệm theo thứ tự ưu tiên
    const candidateExts = ['webp', 'jpg', 'png', 'jpeg'];
    
    // Khởi tạo danh sách các đuôi đã thử
    let tried = (img.dataset.triedExts || '').split(',').filter(Boolean);
    
    const currentUrl = img.src;
    const match = currentUrl.match(/\.([a-zA-Z0-9]+)(\?.*)?$/);
    if (!match) {
        fallbackToErrorImage(img, onFinalFail);
        return;
    }
    
    const currentExt = match[1].toLowerCase();
    if (!tried.includes(currentExt)) {
        tried.push(currentExt);
    }
    
    // Tìm định dạng tiếp theo chưa thử
    const nextExt = candidateExts.find(ext => !tried.includes(ext));
    if (nextExt) {
        tried.push(nextExt);
        img.dataset.triedExts = tried.join(',');
        const newUrl = currentUrl.replace(/\.([a-zA-Z0-9]+)(\?.*)?$/, `.${nextExt}$2`);
        img.src = newUrl;
    } else {
        // Đã thử hết toàn bộ định dạng -> gán ảnh lỗi mặc định
        fallbackToErrorImage(img, onFinalFail);
    }
}

function fallbackToErrorImage(img, onFinalFail) {
    img.onerror = null;
    img.src = 'assets/rem.jpg';
    img.style.maxHeight = '300px';
    if (typeof onFinalFail === 'function') {
        onFinalFail(img);
    }
}

/**
 * Thử tải 1 ảnh qua nhiều định dạng dự phòng (dùng cho tính năng Test tải thử trang)
 * @param {string} url - URL ảnh bắt đầu
 * @param {Function} onDone - Callback (success: boolean, finalUrl: string)
 */
function testSingleImageWithFallback(url, onDone) {
    const candidateExts = ['webp', 'jpg', 'png', 'jpeg'];
    const match = url.match(/\.([a-zA-Z0-9]+)(\?.*)?$/);
    const origExt = match ? match[1].toLowerCase() : 'jpg';
    let tried = [origExt];

    function tryUrl(targetUrl) {
        const img = new Image();
        img.referrerPolicy = 'no-referrer';
        img.onload = () => {
            onDone(true, targetUrl);
        };
        img.onerror = () => {
            const nextExt = candidateExts.find(ext => !tried.includes(ext));
            if (nextExt) {
                tried.push(nextExt);
                const newUrl = targetUrl.replace(/\.([a-zA-Z0-9]+)(\?.*)?$/, `.${nextExt}$2`);
                tryUrl(newUrl);
            } else {
                onDone(false, targetUrl);
            }
        };
        img.src = targetUrl;
    }

    tryUrl(url);
}

/**
 * Render HTML cho một thẻ truyện (Comic Card) dùng chung trên trang chủ, tìm kiếm, thể loại, tác giả.
 * @param {Object} comic - Object chứa thông tin truyện ({id, title, author, cover_filename, gallery_id, genres})
 * @returns {string} Chuỗi HTML của thẻ truyện
 */
function renderComicCard(comic) {
    const coverUrl = api.getCoverUrl(comic.cover_filename);
    const genresHtml = (comic.genres || []).slice(0, 3).map(g =>
        `<span class="tag-chip">${g}</span>`
    ).join('') + ((comic.genres && comic.genres.length > 3) ? `<span class="tag-chip">+${comic.genres.length - 3}</span>` : '');
    const titleSafe = (comic.title || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

    return `
        <div class="comic-card" onclick="window.location.href='detail.html?id=${comic.id}'" style="cursor: pointer;">
            <div class="card-thumb-wrapper">
                ${comic.gallery_id ? `<span class="card-id-badge">${comic.gallery_id}</span>` : ''}
                <button type="button" class="btn-card-delete" onclick="handleDeleteComicCard(event, ${comic.id}, '${titleSafe}')" title="Delete this comic">
                    Delete
                </button>
                <img src="${coverUrl}" alt="${titleSafe}" class="card-thumb" referrerpolicy="no-referrer" onerror="this.src='assets/rem.jpg'">
            </div>
            <div class="card-body">
                <div class="card-title" title="${titleSafe}">${comic.title}</div>
                <div class="card-author">${comic.author || 'Unknown Author'}</div>
                <div class="card-tags">${genresHtml}</div>
            </div>
        </div>
    `;
}

// ==================== 4. GENRE SELECTOR COMPONENT ====================
/**
 * Component for selecting genres via chips
 */
class GenreSelectorComponent {
    constructor(containerId, availableGenres = [], selectedGenres = []) {
        this.container = document.getElementById(containerId);
        this.availableGenres = [...availableGenres];
        this.selectedGenres = new Set(selectedGenres.map(g => g.toLowerCase().trim()));
        this.init();
    }

    init() {
        if (!this.container) return;
        this.render();
    }

    setAvailableGenres(genres) {
        this.availableGenres = [...genres];
        this.render();
    }

    setSelectedGenres(genres) {
        this.selectedGenres = new Set(genres.map(g => g.toLowerCase().trim()));
        this.render();
    }

    getSelectedGenres() {
        return Array.from(this.selectedGenres);
    }

    toggleGenre(genreName) {
        const key = genreName.toLowerCase().trim();
        if (this.selectedGenres.has(key)) {
            this.selectedGenres.delete(key);
        } else {
            this.selectedGenres.add(key);
        }
        this.render();
    }

    render() {
        if (!this.container) return;
        if (this.availableGenres.length === 0) {
            this.container.innerHTML = `
                <div style="padding: 10px; color: var(--text-dim); font-size: 13px;">
                    No genres found in system. <a href="genres.html" style="color: var(--primary);">Click here to add genres</a>
                </div>
            `;
            return;
        }

        this.container.className = 'genre-select-container';
        this.container.innerHTML = this.availableGenres.map(genre => {
            const name = typeof genre === 'string' ? genre : genre.name;
            const isSelected = this.selectedGenres.has(name.toLowerCase().trim());
            return `
                <button type="button" class="genre-chip-btn ${isSelected ? 'active' : ''}" data-name="${name}">
                    <span class="genre-check">${isSelected ? 'Selected' : 'Add'}</span>
                    <span>${name}</span>
                </button>
            `;
        }).join('');

        this.container.querySelectorAll('.genre-chip-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const name = btn.getAttribute('data-name');
                this.toggleGenre(name);
            });
        });
    }
}

// ==================== 5. AUTHOR AUTOCOMPLETE COMPONENT ====================
/**
 * Component for intelligent author suggestions
 */
class AuthorAutocompleteComponent {
    constructor(inputId, authors = []) {
        this.input = document.getElementById(inputId);
        this.authors = [...authors];
        this.selectedIndex = -1;
        this.init();
    }

    setAuthors(authors) {
        this.authors = [...authors];
    }

    init() {
        if (!this.input) return;

        let wrapper = this.input.parentElement;
        if (!wrapper.classList.contains('autocomplete-wrapper')) {
            wrapper = document.createElement('div');
            wrapper.className = 'autocomplete-wrapper';
            this.input.parentNode.insertBefore(wrapper, this.input);
            wrapper.appendChild(this.input);
        }

        this.dropdown = document.createElement('div');
        this.dropdown.className = 'autocomplete-dropdown';
        wrapper.appendChild(this.dropdown);

        this.input.addEventListener('input', () => this.onInput());
        this.input.addEventListener('focus', () => this.onInput());

        this.input.addEventListener('keydown', (e) => {
            const items = this.dropdown.querySelectorAll('.autocomplete-item');
            if (!this.dropdown.classList.contains('active') || items.length === 0) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this.selectedIndex = (this.selectedIndex + 1) % items.length;
                this.updateFocus(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this.selectedIndex = (this.selectedIndex - 1 + items.length) % items.length;
                this.updateFocus(items);
            } else if (e.key === 'Enter') {
                if (this.selectedIndex >= 0 && this.selectedIndex < items.length) {
                    e.preventDefault();
                    items[this.selectedIndex].click();
                }
            } else if (e.key === 'Escape') {
                this.hide();
            }
        });

        document.addEventListener('click', (e) => {
            if (!wrapper.contains(e.target)) {
                this.hide();
            }
        });
    }

    onInput() {
        const query = this.input.value.trim().toLowerCase();
        this.renderDropdown(query);
    }

    updateFocus(items) {
        items.forEach((item, i) => {
            if (i === this.selectedIndex) {
                item.classList.add('focused');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('focused');
            }
        });
    }

    selectAuthor(name) {
        this.input.value = name;
        this.hide();
        this.input.dispatchEvent(new Event('change'));
    }

    hide() {
        this.dropdown.classList.remove('active');
        this.selectedIndex = -1;
    }

    renderDropdown(query) {
        const rawVal = this.input.value.trim();
        const matches = this.authors.filter(a => {
            const name = (typeof a === 'string' ? a : a.name).toLowerCase();
            return !query || name.includes(query);
        });

        const exactMatch = this.authors.some(a => {
            const name = typeof a === 'string' ? a : a.name;
            return name.toLowerCase() === query;
        });

        let html = '';

        if (rawVal && !exactMatch) {
            html += `
                <div class="autocomplete-item autocomplete-item-new" data-val="${rawVal}">
                    <span>Use new author: <b>"${rawVal}"</b></span>
                    <span class="autocomplete-badge">New</span>
                </div>
            `;
        }

        matches.forEach(item => {
            const name = typeof item === 'string' ? item : item.name;
            const count = typeof item === 'object' && item.comic_count !== undefined ? `${item.comic_count} comics` : '';
            html += `
                <div class="autocomplete-item" data-val="${name}">
                    <span>${name}</span>
                    ${count ? `<span class="autocomplete-badge">${count}</span>` : ''}
                </div>
            `;
        });

        if (!html) {
            this.hide();
            return;
        }

        this.dropdown.innerHTML = html;
        this.dropdown.classList.add('active');
        this.selectedIndex = -1;

        this.dropdown.querySelectorAll('.autocomplete-item').forEach(el => {
            el.addEventListener('click', () => {
                const val = el.getAttribute('data-val');
                this.selectAuthor(val);
            });
        });
    }
}
