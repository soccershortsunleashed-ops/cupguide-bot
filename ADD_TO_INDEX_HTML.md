# Instructions: Adding Tournaments and Bulk Actions

## Step 1: Add Tournaments Tab to Navigation

Open `app/templates/index.html`

Find lines 17-20 (Contacts tab):
```html
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="contacts-tab" data-bs-toggle="tab" data-bs-target="#contacts"
            type="button">Контакты</button>
    </li>
```

Add AFTER this block:
```html
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="tournaments-tab" data-bs-toggle="tab" data-bs-target="#tournaments"
            type="button">Турниры</button>
    </li>
```

## Step 2: Add Checkbox to Contacts Table

Find line 261:
```html
                                    <th>ID</th>
```

Replace with:
```html
                                    <th><input type="checkbox" id="selectAllContacts" class="form-check-input"></th>
                                    <th>ID</th>
```

## Step 3: Add Tournaments Tab Content

Find line 278 (end of Contacts Tab):
```html
    </div>
</div>
```

Insert BETWEEN these two lines:
```html
    </div>

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

</div>
```

## Step 4: Add Bulk Actions Toolbar

Find line 281 (before WhatsApp Messages Modal):
```html
<!-- WhatsApp Messages Modal -->
```

Insert BEFORE this line:
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

## Result
- Tournaments tab in navigation
- Checkboxes for contact selection
- Bulk actions toolbar appears when contacts are selected
- Modal for moving contacts to groups
