(function() {
    'use strict';

    // ===== MOCK DATA INICIAL =====
    let users = [
        { id: 'admin', name: 'Administrador', password: 'admin123456' },
        { id: 'joao', name: 'João Silva', password: 'joao12345678' },
        { id: 'maria', name: 'Maria Oliveira', password: 'maria12345678' },
    ];

    // ===== DOM REFS =====
    const form = document.getElementById('userForm');
    const nameInput = document.getElementById('userName');
    const idInput = document.getElementById('userId');
    const passInput = document.getElementById('userPassword');
    const addBtn = document.getElementById('addBtn');
    const clearBtn = document.getElementById('clearBtn');
    const formError = document.getElementById('formError');
    const formSuccess = document.getElementById('formSuccess');

    const searchInput = document.getElementById('searchInput');
    const resultCount = document.getElementById('resultCount');
    const tbody = document.getElementById('userTableBody');

    // Modal
    const editModal = document.getElementById('editModal');
    const editForm = document.getElementById('editForm');
    const editName = document.getElementById('editName');
    const editId = document.getElementById('editId');
    const editPassword = document.getElementById('editPassword');
    const saveEditBtn = document.getElementById('saveEditBtn');
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    const editError = document.getElementById('editError');
    const closeModal = document.querySelector('.close-modal');

    let currentEditId = null; // ID do usuário sendo editado

    // ===== FUNÇÕES AUXILIARES =====
    function showError(element, msg) {
        element.textContent = msg;
        element.classList.add('visible');
        element.classList.remove('hidden');
    }

    function hideError(element) {
        element.classList.remove('visible');
        element.classList.add('hidden');
        element.textContent = '';
    }

    function showSuccess(msg) {
        formSuccess.textContent = msg;
        formSuccess.classList.add('visible');
        formSuccess.classList.remove('hidden');
        setTimeout(() => {
            formSuccess.classList.remove('visible');
            formSuccess.classList.add('hidden');
        }, 3000);
    }

    function renderTable(filter = '') {
        const term = filter.toLowerCase().trim();
        let filtered = users;
        if (term) {
            filtered = users.filter(u =>
                u.name.toLowerCase().includes(term) ||
                u.id.toLowerCase().includes(term)
            );
        }

        resultCount.textContent = `${filtered.length} usuário${filtered.length !== 1 ? 's' : ''}`;

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:#888;">Nenhum usuário encontrado.</td></tr>`;
            return;
        }

        let html = '';
        filtered.forEach(u => {
            html += `
                <tr>
                    <td>${escapeHtml(u.name)}</td>
                    <td>${escapeHtml(u.id)}</td>
                    <td>
                        <div class="actions">
                            <button class="btn-edit" data-id="${escapeHtml(u.id)}">Editar</button>
                            <button class="btn-delete" data-id="${escapeHtml(u.id)}">Excluir</button>
                        </div>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;

        // Atribuir eventos aos botões
        tbody.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => openEditModal(btn.dataset.id));
        });
        tbody.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', () => deleteUser(btn.dataset.id));
        });
    }

    // Escapar HTML para evitar XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ===== CRUD =====
    function addUser(name, id, password) {
        // Verifica se ID já existe
        if (users.some(u => u.id === id)) {
            showError(formError, 'Este ID já está em uso.');
            return false;
        }
        users.push({ id, name, password });
        return true;
    }

    function deleteUser(id) {
        if (!confirm(`Tem certeza que deseja excluir o usuário "${id}"?`)) return;
        users = users.filter(u => u.id !== id);
        renderTable(searchInput.value);
        showSuccess('Usuário excluído com sucesso.');
    }

    function updateUser(id, newName, newPassword) {
        const user = users.find(u => u.id === id);
        if (!user) return false;
        user.name = newName;
        if (newPassword && newPassword.length >= 12) {
            user.password = newPassword;
        }
        return true;
    }

    // ===== MODAL =====
    function openEditModal(id) {
        const user = users.find(u => u.id === id);
        if (!user) return;
        currentEditId = id;
        editName.value = user.name;
        editId.value = user.id;
        editPassword.value = '';
        hideError(editError);
        editModal.classList.remove('hidden');
    }

    function closeEditModal() {
        editModal.classList.add('hidden');
        currentEditId = null;
        editPassword.value = '';
        hideError(editError);
    }

    // ===== EVENTOS =====
    // Form de adicionar
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        hideError(formError);

        const name = nameInput.value.trim();
        const id = idInput.value.trim();
        const password = passInput.value.trim();

        if (!name || !id || !password) {
            showError(formError, 'Todos os campos são obrigatórios.');
            return;
        }
        if (password.length < 12) {
            showError(formError, 'A senha deve ter no mínimo 12 caracteres.');
            return;
        }

        if (addUser(name, id, password)) {
            showSuccess('Usuário adicionado com sucesso!');
            form.reset();
            renderTable(searchInput.value);
        }
        // erro já tratado dentro de addUser
    });

    clearBtn.addEventListener('click', function() {
        form.reset();
        hideError(formError);
        formSuccess.classList.remove('visible');
        formSuccess.classList.add('hidden');
    });

    // Pesquisa
    searchInput.addEventListener('input', function() {
        renderTable(this.value);
    });

    // Modal: salvar edição
    editForm.addEventListener('submit', function(e) {
        e.preventDefault();
        hideError(editError);

        const newName = editName.value.trim();
        const newPassword = editPassword.value.trim();

        if (!newName) {
            showError(editError, 'O nome é obrigatório.');
            return;
        }
        if (newPassword && newPassword.length < 12) {
            showError(editError, 'A nova senha deve ter no mínimo 12 caracteres (ou deixe em branco).');
            return;
        }

        if (updateUser(currentEditId, newName, newPassword)) {
            closeEditModal();
            renderTable(searchInput.value);
            showSuccess('Usuário atualizado com sucesso.');
        } else {
            showError(editError, 'Erro ao atualizar usuário.');
        }
    });

    cancelEditBtn.addEventListener('click', closeEditModal);
    closeModal.addEventListener('click', closeEditModal);

    // Fechar modal clicando fora
    window.addEventListener('click', function(e) {
        if (e.target === editModal) {
            closeEditModal();
        }
    });

    // ===== INICIALIZA =====
    renderTable('');
})();