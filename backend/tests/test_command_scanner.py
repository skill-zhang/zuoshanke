"""高危命令扫描器测试 — 单元测试

覆盖：
  1. 高危模式匹配（文件系统/磁盘/Git/数据库/网络/配置）
  2. 降级逻辑（git 干净工作区、本地环境）
  3. 放行场景（普通命令、安全命令）
  4. 边界情况（sudo 前缀、子 shell、管道、注释）
  5. check_git_clean / check_is_remote_ssh 辅助函数
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# 确保 backend/agent_core 在 path
_BACKEND_DIR = os.path.expanduser("~/zuoshanke/backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agent_core.command_scanner import (
    scan_command,
    check_git_clean,
    check_is_remote_ssh,
    HIGH_RISK_PATTERNS,
)


class TestScanSafeCommands(unittest.TestCase):
    """安全命令 — 全部放行"""

    def test_ls(self):
        self.assertIsNone(scan_command("ls -la"))

    def test_echo(self):
        self.assertIsNone(scan_command("echo hello world"))

    def test_cd(self):
        self.assertIsNone(scan_command("cd /tmp"))

    def test_pip_install(self):
        self.assertIsNone(scan_command("pip install requests"))

    def test_git_commit(self):
        self.assertIsNone(scan_command("git commit -m \"fix bug\""))

    def test_git_push(self):
        self.assertIsNone(scan_command("git push origin main"))

    def test_docker_ps(self):
        self.assertIsNone(scan_command("docker ps -a"))

    def test_docker_compose_up(self):
        self.assertIsNone(scan_command("docker compose up -d"))

    def test_apt_install(self):
        self.assertIsNone(scan_command("apt install nginx"))

    def test_git_pull(self):
        self.assertIsNone(scan_command("git pull origin main"))

    def test_rm_single_file(self):
        self.assertIsNone(scan_command("rm file.txt"))

    def test_rm_rf_node_modules(self):
        self.assertIsNone(scan_command("rm -rf node_modules"))

    def test_empty_string(self):
        self.assertIsNone(scan_command(""))

    def test_rm_specific_path(self):
        self.assertIsNone(scan_command("rm -rf ./temp"))

    def test_dd_to_file(self):
        self.assertIsNone(scan_command("dd if=/dev/zero of=test.img bs=1M count=10"))


class TestBlockFilesystem(unittest.TestCase):
    """文件系统毁灭 — 必须阻断"""

    def test_rm_rf_root(self):
        result = scan_command("rm -rf /")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "filesystem")

    def test_rm_root_plain(self):
        result = scan_command("rm -rf /var/log")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "filesystem")

    def test_sudo_rm_rf_root(self):
        result = scan_command("sudo rm -rf /")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_rm_home(self):
        result = scan_command("rm -rf ~")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_rm_etc(self):
        result = scan_command("rm -rf /etc")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_chmod_recursive_root(self):
        result = scan_command("chmod -R 777 /")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_chown_recursive_root(self):
        result = scan_command("chown -R nobody:nogroup /")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])


class TestBlockDisk(unittest.TestCase):
    """磁盘毁灭 — 必须阻断"""

    def test_dd_zero_to_sda(self):
        result = scan_command("dd if=/dev/zero of=/dev/sda bs=4M")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "disk")

    def test_mkfs_sda(self):
        result = scan_command("mkfs.ext4 /dev/sda1")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_shred_sda(self):
        result = scan_command("shred /dev/sda")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])


class TestBlockGit(unittest.TestCase):
    """Git 毁灭 — 按工作区状态降级"""

    def test_git_reset_hard_no_cwd(self):
        """无 cwd 时不降级（保守策略）"""
        result = scan_command("git reset --hard HEAD")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "git")

    def test_git_reset_hard_dirty(self):
        """工作区脏 → 阻断"""
        with patch("agent_core.command_scanner.check_git_clean", return_value=False):
            result = scan_command("git reset --hard HEAD", cwd="/tmp")
            self.assertIsNotNone(result)
            self.assertTrue(result["block"])

    def test_git_reset_hard_clean(self):
        """工作区干净 → 降级放行"""
        with patch("agent_core.command_scanner.check_git_clean", return_value=True):
            result = scan_command("git reset --hard HEAD", cwd="/tmp")
            self.assertIsNotNone(result)
            self.assertFalse(result["block"])  # 降级

    def test_git_branch_D_main(self):
        result = scan_command("git branch -D main")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "git")

    def test_git_clean_fd(self):
        result = scan_command("git clean -fd")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])


class TestBlockDatabase(unittest.TestCase):
    """数据库毁灭 — 必须阻断"""

    def test_drop_database(self):
        result = scan_command("DROP DATABASE mydb;")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "database")

    def test_drop_table(self):
        result = scan_command("DROP TABLE users;")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_truncate(self):
        result = scan_command("TRUNCATE TABLE logs;")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_delete_no_where(self):
        result = scan_command("DELETE FROM users;")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_delete_with_where(self):
        """DELETE 有 WHERE → 放行"""
        self.assertIsNone(scan_command("DELETE FROM users WHERE id = 1;"))


class TestBlockNetwork(unittest.TestCase):
    """网络自锁 — 仅远程环境阻断"""

    def test_iptables_f_local(self):
        """本地环境 → 降级"""
        with patch("agent_core.command_scanner.check_is_remote_ssh", return_value=False):
            result = scan_command("iptables -F")
            self.assertIsNotNone(result)
            self.assertFalse(result["block"])

    def test_iptables_f_remote(self):
        """远程环境 → 阻断"""
        with patch("agent_core.command_scanner.check_is_remote_ssh", return_value=True):
            result = scan_command("iptables -F")
            self.assertIsNotNone(result)
            self.assertTrue(result["block"])

    def test_ufw_disable_local(self):
        with patch("agent_core.command_scanner.check_is_remote_ssh", return_value=False):
            result = scan_command("ufw disable")
            self.assertIsNotNone(result)
            self.assertFalse(result["block"])

    def test_systemctl_stop_ssh_remote(self):
        with patch("agent_core.command_scanner.check_is_remote_ssh", return_value=True):
            result = scan_command("systemctl stop ssh")
            self.assertIsNotNone(result)
            self.assertTrue(result["block"])


class TestBlockConfig(unittest.TestCase):
    """配置/认证毁灭 — 必须阻断"""

    def test_rm_ssh_dir(self):
        result = scan_command("rm -rf ~/.ssh/authorized_keys")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "config")

    def test_kill_9_neg1(self):
        result = scan_command("kill -9 -1")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_passwd_lock_root(self):
        result = scan_command("passwd -l root")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])


class TestBlockDocker(unittest.TestCase):
    """Docker 毁灭 — 必须阻断"""

    def test_docker_system_prune_volumes(self):
        result = scan_command("docker system prune -a --volumes")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "docker")

    def test_docker_rm_all(self):
        result = scan_command("docker rm -f $(docker ps -aq)")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_docker_volume_rm_all(self):
        result = scan_command("docker volume rm $(docker volume ls -q)")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_docker_compose_down_v(self):
        result = scan_command("docker compose down -v")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])


class TestBlockPackage(unittest.TestCase):
    """包管理器毁灭 — 必须阻断"""

    def test_apt_remove_python3(self):
        result = scan_command("apt remove python3")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])
        self.assertEqual(result["category"], "package")

    def test_apt_remove_systemd(self):
        result = scan_command("apt remove systemd -y")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_dpkg_purge_python3(self):
        result = scan_command("dpkg --purge python3")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])


class TestEdgeCases(unittest.TestCase):
    """边界情况"""

    def test_pipe_with_rm_rf(self):
        """管道中包含高危命令"""
        result = scan_command("echo y | rm -rf /")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_subshell_with_rm(self):
        """子 shell 中包含高危命令"""
        result = scan_command("$(rm -rf /)")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_sudo_rm_rf_root(self):
        result = scan_command("sudo rm -rf /")
        self.assertIsNotNone(result)
        self.assertTrue(result["block"])

    def test_select_from_table(self):
        """SELECT 语句放行"""
        self.assertIsNone(scan_command("SELECT * FROM users"))

    def test_dd_to_normal_file(self):
        """dd 到普通文件放行"""
        self.assertIsNone(scan_command("dd if=/dev/zero of=output.bin bs=1024 count=100"))

    def test_rm_relative_path(self):
        """rm 相对路径放行"""
        self.assertIsNone(scan_command("rm -rf ./build/"))


class TestAuxFunctions(unittest.TestCase):
    """辅助函数测试"""

    @patch("agent_core.command_scanner.subprocess.run")
    def test_git_clean_clean(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", text=True)
        # 需要正确处理 text=True 时的返回值
        mock_run.return_value.stdout = ""
        result = check_git_clean("/tmp")
        self.assertTrue(result)

    @patch("agent_core.command_scanner.subprocess.run")
    def test_git_clean_dirty(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = " M foo.py\n"
        result = check_git_clean("/tmp")
        self.assertFalse(result)

    @patch("agent_core.command_scanner.subprocess.run")
    def test_git_clean_not_repo(self, mock_run):
        mock_run.return_value.returncode = 128
        mock_run.return_value.stdout = ""
        result = check_git_clean("/tmp")
        self.assertIsNone(result)

    def test_check_remote_ssh_local(self):
        """本地环境（无 SSH 环境变量）→ False"""
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(check_is_remote_ssh())

    def test_check_remote_ssh_connected(self):
        """通过 SSH 连接 → True"""
        with patch.dict(os.environ, {"SSH_CONNECTION": "192.168.1.1 22 10.0.0.1 22"}):
            self.assertTrue(check_is_remote_ssh())

    def test_check_remote_ssh_client(self):
        with patch.dict(os.environ, {"SSH_CLIENT": "192.168.1.1 54321 22"}):
            self.assertTrue(check_is_remote_ssh())


class TestPatternCount(unittest.TestCase):
    """验证模式清单完整性"""

    def test_patterns_not_empty(self):
        self.assertGreater(len(HIGH_RISK_PATTERNS), 30)

    def test_all_patterns_have_valid_structure(self):
        for i, (pat, cat, desc) in enumerate(HIGH_RISK_PATTERNS):
            with self.subTest(i=i):
                self.assertIsInstance(pat, str)
                self.assertIsInstance(cat, str)
                self.assertIsInstance(desc, str)
                self.assertIn(cat, {"filesystem", "disk", "git", "database",
                                    "network", "docker", "package", "config",
                                    "exfil", "ssrf"})


if __name__ == "__main__":
    unittest.main()
