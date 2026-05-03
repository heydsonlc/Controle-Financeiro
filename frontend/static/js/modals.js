(function () {
    function modalEstaAberto(modal) {
        if (!modal) return false;
        if (modal.classList.contains('open')) return true;
        const displayInline = (modal.getAttribute('style') || '').toLowerCase();
        return displayInline.includes('display: block') || displayInline.includes('display:block') ||
            displayInline.includes('display: flex') || displayInline.includes('display:flex');
    }

    function resetarScrollModal(modal) {
        if (!modalEstaAberto(modal)) return;

        window.requestAnimationFrame(function () {
            const alvos = modal.querySelectorAll('.modal-content, .modal-body, .modal-content > form');
            alvos.forEach(function (elemento) {
                elemento.scrollTop = 0;
            });
        });
    }

    function observarModal(modal) {
        if (!modal) return;

        const observer = new MutationObserver(function () {
            resetarScrollModal(modal);
        });

        observer.observe(modal, {
            attributes: true,
            attributeFilter: ['class', 'style']
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.modal').forEach(observarModal);
    });
}());
