// static/js/scrape.js
/** 刮削页逻辑模块 (MVP) */

const ScrapeAPI = {
    async getList(page = 1, perPage = 50, filter = 'all', sort = 'code') {
        const params = new URLSearchParams({
            page: page.toString(),
            per_page: perPage.toString(),
            filter: filter,
            sort: sort
        });

        const response = await fetch(`/api/scrape?${params}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    },

    async scrapeSingle(fileId) {
        const response = await fetch(`/api/scrape/${fileId}`, {
            method: 'POST'
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return await response.json();
    }
};

const ScrapePage = {
    currentPage: 1,
    perPage: 50,
    items: [],

    async loadList() {
        try {
            const result = await ScrapeAPI.getList(
                this.currentPage,
                this.perPage,
                state.scrapeFilter,
                state.scrapeSort
            );
            this.items = result.items || [];
            this.render();
        } catch (error) {
            console.error('加载刮削列表失败:', error);
            alert('加载失败: ' + error.message);
        }
    },

    async handleScrape(fileId, code) {
        if (!confirm(`确认刮削 ${code}?`)) {
            return;
        }

        const btn = document.querySelector(`[data-file-id="${fileId}"] .scrape-btn`);
        if (btn) {
            btn.disabled = true;
            btn.textContent = '刮削中...';
        }

        try {
            const result = await ScrapeAPI.scrapeSingle(fileId);

            if (result.success) {
                alert(`${code} 刮削成功!`);
                await this.loadList();  // 刷新列表
            } else {
                alert(`${code} 刮削失败: ${result.error}`);
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '刮削';
                }
            }
        } catch (error) {
            console.error('刮削失败:', error);
            alert(`刮削失败: ${error.message}`);
            if (btn) {
                btn.disabled = false;
                btn.textContent = '刮削';
            }
        }
    },

    render() {
        const tbody = document.querySelector('#scrape-table tbody');
        if (!tbody) return;

        if (this.items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center">暂无数据</td></tr>';
            return;
        }

        tbody.innerHTML = this.items.map(item => `
            <tr data-file-id="${item.file_id}">
                <td>${item.code}</td>
                <td>${this.renderStatus(item.scrape_status)}</td>
                <td>${item.last_scrape_at || '-'}</td>
                <td>
                    <button class="scrape-btn" data-action="scrape">刮削</button>
                </td>
            </tr>
        `).join('');

        // 绑定事件
        tbody.querySelectorAll('[data-action="scrape"]').forEach(btn => {
            btn.addEventListener('click', () => {
                const row = btn.closest('tr');
                const fileId = parseInt(row.dataset.fileId);
                const code = row.querySelector('td:first-child').textContent;
                this.handleScrape(fileId, code);
            });
        });
    },

    renderStatus(status) {
        const statusMap = {
            'pending': '<span class="status status-pending">待刮削</span>',
            'success': '<span class="status status-success">已刮削</span>',
            'failed': '<span class="status status-failed">刮削失败</span>'
        };
        return statusMap[status] || status;
    },

    init() {
        this.loadList();

        // 筛选器
        document.querySelector('#scrape-filter')?.addEventListener('change', (e) => {
            state.scrapeFilter = e.target.value;
            this.currentPage = 1;
            this.loadList();
        });

        // 排序器
        document.querySelector('#scrape-sort')?.addEventListener('change', (e) => {
            state.scrapeSort = e.target.value;
            this.loadList();
        });
    }
};
