(function (window) {
    function mergeSection(target, section) {
        Object.defineProperties(target, Object.getOwnPropertyDescriptors(section));
        return target;
    }

    function createApp() {
        const app = {};

        mergeSection(app, window.NoctraState.createState());
        mergeSection(app, window.NoctraUtils.createUtils());
        mergeSection(app, window.NoctraRender.createRender());
        mergeSection(app, window.NoctraFeatures.createFeatures());

        return app;
    }

    window.NoctraApp = {
        createApp
    };

    window.app = function app() {
        return window.NoctraApp.createApp();
    };
})(window);
