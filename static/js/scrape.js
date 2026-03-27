// static/js/scrape.js
/** Scrape API module — state and rendering handled by Alpine.js */

const ScrapeAPI = {
    async getList(params = {}) {
        const searchParams = new URLSearchParams({
            page: String(params.page || 1),
            per_page: String(params.perPage || 50),
            filter: params.filter || 'all',
            sort: params.sort || 'code'
        });

        const response = await fetch(`/api/scrape?${searchParams}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return data;
    },

    async createJob(fileIds) {
        const response = await fetch('/api/scrape/jobs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ file_ids: fileIds })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || '创建刮削任务失败');
        }
        return data;
    },

    async getJob(jobId) {
        const response = await fetch(`/api/scrape/jobs/${jobId}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || '获取刮削任务失败');
        }
        return data;
    },

    async cancelJob(jobId) {
        const response = await fetch(`/api/scrape/jobs/${jobId}/cancel`, {
            method: 'POST'
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || '取消刮削任务失败');
        }
        return data;
    }
};
