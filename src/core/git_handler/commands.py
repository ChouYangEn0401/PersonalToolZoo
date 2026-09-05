from src.core.language_manager import lm


def get_commands_configs():
    return {
        # === Branch 相關 ===
        'checkout_branch': {
            'name': lm.t('cmd.checkout_branch.name'),
            'base_cmd': 'checkout',
            'params': [
                {'name': 'branch', 'label': lm.t('cmd.checkout_branch.param.branch'), 'required': True, 'type': 'text',
                 'autocomplete': 'branch'},
                {'name': 'create', 'label': lm.t('cmd.checkout_branch.param.create'), 'required': True, 'type': 'toggle', 'default': True}
            ]
        },

        # === Rebase 系列 ===
        'rebase_branch': {
            'name': lm.t('cmd.rebase_branch.name'),
            'base_cmd': 'rebase',
            'params': [
                {'name': 'branch', 'label': lm.t('cmd.rebase_branch.param.branch'), 'required': True, 'type': 'text', 'default': 'main',
                 'autocomplete': 'branch'}
            ]
        },
        'rebase_interactive': {
            'name': lm.t('cmd.rebase_interactive.name'),
            'base_cmd': 'rebase',
            'params': [
                {'name': 'commit', 'label': lm.t('cmd.rebase_interactive.param.commit'), 'required': True, 'type': 'text',
                 'default': 'HEAD~5', 'autocomplete': 'commit'},
                {'name': 'interactive', 'label': lm.t('cmd.rebase_interactive.param.interactive'), 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },

        # === Cherry-pick 系列 ===
        'cherry_pick': {
            'name': lm.t('cmd.cherry_pick.name'),
            'base_cmd': 'cherry-pick',
            'params': [
                {'name': 'commit', 'label': lm.t('cmd.cherry_pick.param.commit'), 'required': True, 'type': 'text',
                 'autocomplete': 'commit'},
                {'name': 'no_commit', 'label': lm.t('cmd.cherry_pick.param.no_commit'), 'required': False, 'type': 'toggle'}
            ]
        },

        # === restore_file_from_commit 系列 ===
        'restore_file_from_commit': {
            'name': lm.t('cmd.restore_file.name'),
            'base_cmd': 'custom',
            'params': [
                {'name': 'commit', 'label': lm.t('cmd.restore_file.param.commit'), 'type': 'text', 'required': True, 'default': 'HEAD~1'}
            ]
        },

        # === Reset 系列 ===
        'reset_soft': {
            'name': lm.t('cmd.reset_soft.name'),
            'base_cmd': 'reset',
            'params': [
                {'name': 'commit', 'label': lm.t('cmd.reset_soft.param.commit'), 'required': True, 'type': 'text',
                 'default': 'HEAD~1', 'autocomplete': 'commit'},
                {'name': 'soft', 'label': lm.t('cmd.reset_soft.param.soft'), 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },
        'reset_hard': {
            'name': lm.t('cmd.reset_hard.name'),
            'base_cmd': 'reset',
            'danger': True,
            'params': [
                {'name': 'commit', 'label': lm.t('cmd.reset_hard.param.commit'), 'required': True, 'type': 'text',
                 'default': 'HEAD~1', 'autocomplete': 'commit'},
                {'name': 'hard', 'label': lm.t('cmd.reset_hard.param.hard'), 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },

        # === Stash 系列 ===
        'stash_commit': {
            'name': lm.t('cmd.stash_commit.name'),
            'base_cmd': 'custom',
            'custom_handler': 'handle_stash_commit',
            'params': [
                {'name': 'message', 'label': lm.t('cmd.stash_commit.param.message'), 'required': False, 'type': 'text',
                 'default': 'WIP'}
            ]
        },

        # === Commit 系列 ===
        'commit_message': {
            'name': lm.t('cmd.commit_message.name'),
            'base_cmd': 'commit',
            'params': [
                {'name': 'message', 'label': lm.t('cmd.commit_message.param.message'), 'required': True, 'type': 'text'}
            ]
        },
        'commit_amend': {
            'name': lm.t('cmd.commit_amend.name'),
            'base_cmd': 'commit',
            'params': [
                {'name': 'message', 'label': lm.t('cmd.commit_amend.param.message'), 'required': False, 'type': 'text'},
                {'name': 'amend', 'label': lm.t('cmd.commit_amend.param.amend'), 'required': True, 'type': 'toggle',
                 'default': True},
                {'name': 'no_edit', 'label': lm.t('cmd.commit_amend.param.no_edit'), 'required': False, 'type': 'toggle'}
            ]
        },
        'commit_squash': {
            'name': lm.t('cmd.commit_squash.name'),
            'base_cmd': 'commit',
            'params': [
                {'name': 'message', 'label': lm.t('cmd.commit_squash.param.message'), 'required': True, 'type': 'text', 'default': 's'}
            ]
        },

        # === Push 系列 ===
        'force_push': {
            'name': lm.t('cmd.force_push.name'),
            'base_cmd': 'push',
            'danger': True,
            'params': [
                {'name': 'remote', 'label': lm.t('cmd.force_push.param.remote'), 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'branch', 'label': lm.t('cmd.force_push.param.branch'), 'required': False, 'type': 'text',
                 'autocomplete': 'branch'},
                {'name': 'force', 'label': lm.t('cmd.force_push.param.force'), 'required': True, 'type': 'toggle', 'default': True},
                {'name': 'force_with_lease', 'label': lm.t('cmd.force_push.param.force_with_lease'), 'required': False,
                 'type': 'toggle'}
            ]
        },

        # === Branch 系列 ===
        'delete_branch': {
            'name': lm.t('cmd.delete_branch.name'),
            'base_cmd': 'branch',
            'danger': True,
            'params': [
                {'name': 'branch', 'label': lm.t('cmd.delete_branch.param.branch'), 'required': True, 'type': 'text',
                 'autocomplete': 'branch'},
                {'name': 'force_delete', 'label': lm.t('cmd.delete_branch.param.force_delete'), 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },
        'delete_remote_branch': {
            'name': lm.t('cmd.delete_remote_branch.name'),
            'base_cmd': 'push',
            'danger': True,
            'params': [
                {'name': 'remote', 'label': lm.t('cmd.delete_remote_branch.param.remote'), 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'branch', 'label': lm.t('cmd.delete_remote_branch.param.branch'), 'required': True, 'type': 'text', 'autocomplete': 'branch'},
                {'name': 'delete', 'label': lm.t('cmd.delete_remote_branch.param.delete'), 'required': True, 'type': 'toggle',
                 'default': True}
            ]
        },
        'prune_branches': {
            'name': lm.t('cmd.prune.name'),
            'base_cmd': 'custom',
            'custom_handler': 'handle_prune_branches',
            'params': [
                {'name': 'remote', 'label': lm.t('cmd.prune.param.remote'), 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'dry_run', 'label': lm.t('cmd.prune.param.dry_run'), 'required': False, 'type': 'toggle'}
            ]
        },

        # === Checkout (switch to branch or commit) ===
        'checkout': {
            'name': lm.t('cmd.checkout.name'),
            'base_cmd': 'checkout',
            'params': [
                {'name': 'branch', 'label': lm.t('cmd.checkout.param.branch'), 'required': True, 'type': 'text',
                 'autocomplete': 'branch'},
                {'name': 'create', 'label': lm.t('cmd.checkout.param.create'), 'required': False, 'type': 'toggle'}
            ]
        },

        # === Tag 系列 ===
        'create_tag': {
            'name': lm.t('cmd.create_tag.name'),
            'base_cmd': 'tag',
            'params': [
                {'name': 'tag', 'label': lm.t('cmd.create_tag.param.tag'), 'required': True, 'type': 'text', 'autocomplete': 'tag'},
                {'name': 'message', 'label': lm.t('cmd.create_tag.param.message'), 'required': False, 'type': 'text'},
                {'name': 'commit', 'label': lm.t('cmd.create_tag.param.commit'), 'required': False, 'type': 'text',
                 'autocomplete': 'commit'}
            ]
        },
        'delete_tag': {
            'name': lm.t('cmd.delete_tag.name'),
            'base_cmd': 'tag',
            'danger': True,
            'params': [
                {'name': 'tag', 'label': lm.t('cmd.delete_tag.param.tag'), 'required': True, 'type': 'text',
                 'autocomplete': 'tag'},
                {'name': 'delete', 'label': lm.t('cmd.delete_tag.param.delete'), 'required': True, 'type': 'toggle', 'default': True}
            ]
        },
        'delete_remote_tag': {
            'name': lm.t('cmd.delete_remote_tag.name'),
            'base_cmd': 'push',
            'danger': True,
            'params': [
                {'name': 'remote', 'label': lm.t('cmd.delete_remote_tag.param.remote'), 'required': False, 'type': 'text', 'default': 'origin'},
                {'name': 'tag', 'label': lm.t('cmd.delete_remote_tag.param.tag'), 'required': True, 'type': 'text', 'autocomplete': 'tag'},
                {'name': 'delete', 'label': lm.t('cmd.delete_remote_tag.param.delete'), 'required': True, 'type': 'toggle', 'default': True}
            ]
        },

        # === 其他 ===
        'checkout_file': {
            'name': lm.t('cmd.checkout_file.name'),
            'base_cmd': 'checkout',
            'params': [
                {'name': 'source', 'label': lm.t('cmd.checkout_file.param.source'), 'required': False, 'type': 'text',
                 'autocomplete': 'commit'},
                {'name': 'file', 'label': lm.t('cmd.checkout_file.param.file'), 'required': True, 'type': 'text'}
            ]
        }
    }