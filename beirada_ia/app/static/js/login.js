(function() {
    const form = document.getElementById('loginForm');
    const username = document.getElementById('username');
    const password = document.getElementById('password');
    const loginBtn = document.getElementById('loginBtn');
    const errorMsg = document.getElementById('errorMsg');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        errorMsg.classList.remove('visible');
        errorMsg.textContent = '';

        const user = username.value.trim();
        const pass = password.value.trim();

        if (!user || !pass) {
            showError('Preencha ambos os campos.');
            return;
        }

        loginBtn.disabled = true;
        loginBtn.textContent = 'Entrando...';

        try {
            // Simulação – substitua por chamada real
            await simulateLogin(user, pass);
            window.location.href = '../dashboard/dashboard.html';
        } catch (err) {
            showError(err.message || 'Credenciais inválidas.');
            loginBtn.disabled = false;
            loginBtn.textContent = 'Entrar';
        }
    });

    function simulateLogin(user, pass) {
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                if (user === 'admin' && pass === 'admin123') resolve();
                else reject(new Error('Usuário ou senha incorretos.'));
            }, 1000);
        });
    }

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.classList.add('visible');
    }

    username.addEventListener('input', () => errorMsg.classList.remove('visible'));
    password.addEventListener('input', () => errorMsg.classList.remove('visible'));
})();