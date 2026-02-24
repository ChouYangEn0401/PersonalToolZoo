
def get_commands_configs():
    return {
        # === Branch 相關 ===
        'checkout_branch': {
            'name': '建立並切換分支',
            'base_cmd': 'checkout',
            'params': [
                {'name': 'branch', 'label': '新分支名稱', 'required': True, 'type': 'text',
                 'autocomplete': 'branch'},
                {'name': 'create', 'label': '建立新分支 (-b)', 'required': True, 'type': 'toggle', 'default': True}
            ]
        },

        # === Rebase 系列 ===
        'rebase_branch': {
            'name': 'Rebase 到分支',
            'base_cmd': 'rebase',
            'params': [
                {'name': 'branch', 'label': '目標分支', 'required': True, 'type': 'text', 'default': 'main',
                 'autocomplete': 'branch'}
            ]
        },
        'rebase_interactive': {
            'name': 'Rebase Interactive',
            'base_cmd': 'rebase',
            'params': [
                {'name': 'commit', 'label': '起始 Commit (HEAD~N 或 Hash)', 'required': True, 'type': 'text',
                 'default': 'HEAD~5', 'autocomplete': 'commit'},
                {'name': 'interactive', 'label': '互動模式 (-i)', 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },

        # === Cherry-pick 系列 ===
        'cherry_pick': {
            'name': 'Cherry-pick',
            'base_cmd': 'cherry-pick',
            'params': [
                {'name': 'commit', 'label': 'Commit Hash (可多個，空格分隔)', 'required': True, 'type': 'text',
                 'autocomplete': 'commit'},
                {'name': 'no_commit', 'label': '不自動提交 (-n)', 'required': False, 'type': 'toggle'}
            ]
        },

        # === restore_file_from_commit 系列 ===
        'restore_file_from_commit': {
            'name': '從特定提交還原檔案',
            'base_cmd': 'custom',  # 使用自訂邏輯
            'params': [
                {'name': 'commit', 'label': 'Commit Hash', 'type': 'text', 'required': True, 'default': 'HEAD~1'}
            ]
        },

        # === Reset 系列 ===
        'reset_soft': {
            'name': 'Soft Reset',
            'base_cmd': 'reset',
            'params': [
                {'name': 'commit', 'label': '目標 Commit (HEAD~N 或 Hash)', 'required': True, 'type': 'text',
                 'default': 'HEAD~1', 'autocomplete': 'commit'},
                {'name': 'soft', 'label': 'Soft 模式 (保留修改)', 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },
        'reset_hard': {
            'name': 'Hard Reset',
            'base_cmd': 'reset',
            'danger': True,
            'params': [
                {'name': 'commit', 'label': '目標 Commit (HEAD~N 或 Hash)', 'required': True, 'type': 'text',
                 'default': 'HEAD~1', 'autocomplete': 'commit'},
                {'name': 'hard', 'label': 'Hard 模式 (捨棄所有修改 ⚠️)', 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },

        # === Stash 系列 ===
        'stash_commit': {
            'name': 'Stash → Commit Squash',
            'base_cmd': 'custom',
            'custom_handler': 'handle_stash_commit',
            'params': [
                {'name': 'message', 'label': 'Commit 訊息 (預設: WIP)', 'required': False, 'type': 'text',
                 'default': 'WIP'}
            ]
        },

        # === Commit 系列 ===
        'commit_message': {
            'name': 'Commit 訊息',
            'base_cmd': 'commit',
            'params': [
                {'name': 'message', 'label': 'Commit 訊息', 'required': True, 'type': 'text'}
            ]
        },
        'commit_amend': {
            'name': 'Commit Amend',
            'base_cmd': 'commit',
            'params': [
                {'name': 'message', 'label': 'Commit 訊息 (留空則不改)', 'required': False, 'type': 'text'},
                {'name': 'amend', 'label': '修改上次提交 (--amend)', 'required': True, 'type': 'toggle',
                 'default': True},
                {'name': 'no_edit', 'label': '不修改訊息 (--no-edit)', 'required': False, 'type': 'toggle'}
            ]
        },
        'commit_squash': {
            'name': 'Squash Commit',
            'base_cmd': 'commit',
            'params': [
                {'name': 'message', 'label': 'Squash 訊息', 'required': True, 'type': 'text', 'default': 's'}
            ]
        },

        # === Push 系列 ===
        'force_push': {
            'name': 'Force Push',
            'base_cmd': 'push',
            'danger': True,
            'params': [
                {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'branch', 'label': '分支名稱 (留空=當前)', 'required': False, 'type': 'text',
                 'autocomplete': 'branch'},
                {'name': 'force', 'label': '強制推送 (-f)', 'required': True, 'type': 'toggle', 'default': True},
                {'name': 'force_with_lease', 'label': '安全強推 (--force-with-lease)', 'required': False,
                 'type': 'toggle'}
            ]
        },

        # === Branch 系列 ===
        'delete_branch': {
            'name': 'Delete Branch',
            'base_cmd': 'branch',
            'danger': True,
            'params': [
                {'name': 'branch', 'label': '分支名稱 (可多個，空格分隔)', 'required': True, 'type': 'text',
                 'autocomplete': 'branch'},
                {'name': 'force_delete', 'label': '強制刪除 (-D)', 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },
        'delete_remote_branch': {
            'name': 'Delete Remote Branch',
            'base_cmd': 'push',
            'danger': True,
            'params': [
                {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'branch', 'label': '分支名稱', 'required': True, 'type': 'text', 'autocomplete': 'branch'},
                {'name': 'delete', 'label': '刪除遠端分支 (--delete)', 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },
        'prune_branches': {
            'name': 'Prune Branches',
            'base_cmd': 'custom',
            'custom_handler': 'handle_prune_branches',
            'params': [
                {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'dry_run', 'label': '僅預覽 (--dry-run)', 'required': False, 'type': 'toggle'}
            ]
        },

        # === Tag 系列 ===
        'create_tag': {
            'name': 'Create Tag',
            'base_cmd': 'tag',
            'params': [
                {'name': 'tag', 'label': 'Tag 名稱', 'required': True, 'type': 'text', 'autocomplete': 'tag'},
                {'name': 'message', 'label': 'Tag 訊息 (-m)', 'required': False, 'type': 'text'},
                {'name': 'commit', 'label': '指定 Commit (留空=HEAD)', 'required': False, 'type': 'text',
                 'autocomplete': 'commit'}
            ]
        },
        'delete_tag': {
            'name': 'Delete Tag',
            'base_cmd': 'tag',
            'danger': True,
            'params': [
                {'name': 'tag', 'label': 'Tag 名稱 (可多個，空格分隔)', 'required': True, 'type': 'text',
                 'autocomplete': 'tag'},
                {'name': 'delete', 'label': '刪除標籤 (-d)', 'required': True, 'type': 'toggle', 'default': True}
            ]
        },
        'delete_remote_tag': {
            'name': '刪除遠端標籤',
            'base_cmd': 'push',
            'danger': True,
            'params': [
                {'name': 'remote', 'label': '遠端名稱', 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'tag', 'label': 'Tag 名稱', 'required': True, 'type': 'text', 'autocomplete': 'tag'},
                {'name': 'delete', 'label': '刪除 (--delete)', 'required': True, 'type': 'toggle', 'default': True}
            ]
        },

        # === 其他 ===
        'checkout_file': {
            'name': 'Checkout File',
            'base_cmd': 'checkout',
            'params': [
                {'name': 'source', 'label': '來源 (Commit/Branch，留空=HEAD)', 'required': False, 'type': 'text',
                 'autocomplete': 'commit'},
                {'name': 'file', 'label': '檔案路徑', 'required': True, 'type': 'text'}
            ]
        }
    }