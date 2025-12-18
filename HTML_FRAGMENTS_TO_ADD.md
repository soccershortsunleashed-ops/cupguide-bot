# HTML Фрагменты для добавления

## 1. Добавить вкладку "Турниры" в навигацию

**Где:** После строки 19 (после закрывающего `</li>` вкладки Контакты)

```html
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="tournaments-tab" data-bs-toggle="tab" data-bs-target="#tournaments"
            type="button">Турниры</button>
    </li>
```

## 2. Добавить чекбокс в заголовок таблицы контактов

**Где:** Строка 261, заменить существующую строку `<th>ID</th>` на:

```html
                                    <th><input type="checkbox" id="selectAllContacts" class="form-check-input"></th>
                                    <th>ID</th>
```

## 3. Добавить вкладку турниров (контент)

**Где:** После строки 278 (после `</div>` которая закрывает Contacts Tab), ПЕРЕД строкой 279 `</div>` которая закрывает `tab-content`

```html
    <!-- Tournaments Tab -->
    <div class="tab-pane fade" id="tournaments" role="tabpanel">
        <div class="d-flex justify-content-between align-items-center mb-3">
            <h3>Турниры</h3>
            <button class="btn btn-primary" id="refreshTournamentsBtn">
                <i class="bi bi-arrow-clockwise"></i> Обновить
            </button>
        </div>
        <div id="tournamentsList" class="row g-4">
            <!-- Tournaments will be loaded here -->
        </div>
    </div>
```

## 4. Добавить панель Bulk Actions

**Где:** После строки 279 (после закрывающего `</div>` для `tab-content`), ПЕРЕД строкой 281 (перед `<!-- WhatsApp Messages Modal -->`)

```html

<!-- Bulk Actions Toolbar -->
<div id="bulkActionsToolbar"
    class="alert alert-info d-none position-fixed bottom-0 start-50 translate-middle-x mb-3"
    style="z-index: 1050; min-width: 400px;">
    <div class="d-flex justify-content-between align-items-center">
        <span>Выбрано: <strong id="selectedCount">0</strong></span>
        <div class="btn-group">
            <button class="btn btn-sm btn-primary" onclick="openBulkMoveModal()">
                <i class="bi bi-folder"></i> Переместить
            </button>
            <button class="btn btn-sm btn-danger" onclick="bulkDeleteContacts()">
                <i class="bi bi-trash"></i> Удалить
            </button>
        </div>
    </div>
</div>

<!-- Bulk Move Modal -->
<div class="modal fade" id="bulkMoveModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Переместить контакты</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <div class="mb-3">
                    <label class="form-label">Выберите группу</label>
                    <select class="form-select" id="bulkMoveGroupSelect">
                        <option value="Общая">Общая</option>
                        <option value="Тренеры по футболу">Тренеры по футболу</option>
                        <option value="Экипировка">Экипировка</option>
                    </select>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Отмена</button>
                <button type="button" class="btn btn-primary" onclick="submitBulkMove()">Переместить</button>
            </div>
        </div>
    </div>
</div>
```

## Инструкция

1. Откройте `app/templates/index.html` в редакторе
2. Вставьте фрагменты в указанных местах (по порядку сверху вниз)
3. Сохраните файл
4. Обновите браузер

После этого у вас появятся:
- ✅ Вкладка "Турниры" в навигации
- ✅ Чекбоксы для выбора контактов
- ✅ Панель bulk actions внизу экрана при выборе контактов
- ✅ Модальное окно для перемещения контактов в группу
