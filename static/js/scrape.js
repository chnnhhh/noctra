// static/js/scrape.js
/** Scrape API module — state and rendering handled by Alpine.js */

const ScrapeAPI = {
    async getList(params = {}) {
        const searchParams = new URLSearchParams({
            page: (params.page || 1).toString(),
            per_page: (params.perPage || 50).toString(),
            filter: params.filter || 'all',
            sort: params.sort || 'code'
        });

        const response = await fetch(`/api/scrape?${searchParams}`);
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return await response.json();
    },

    async scrapeSingle(fileId) {
        const response = await fetch(`/api/scrape/${fileId}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return await response.json();
    }
};
