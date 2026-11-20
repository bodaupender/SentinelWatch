"""
Service and Process Detections for SentinelWatch.

Defensive detections for Windows process and service telemetry.
Implements the detection rules specified in Phase 3 Steps 2-4.
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from .rule_model import (
    DetectionRule, DetectionResult, RuleCategory, RuleSeverity,
    RuleStatus, RuleType
)


# --- Rule: Unquoted Service Path Detection ---

UNQUOTED_SERVICE_PATH = DetectionRule(
    rule_id="SV-001",
    rule_name="Unquoted Service Path Detection",
    description="Detects Windows services with unquoted service paths that could lead to hijacking",
    category="service",
    severity="high",
    confidence=70.0,
    condition='service_binary_path matches regex "^[A-Za-z]:\\\\[^\"\\s]+\\s+[^/]" and not (service_binary_path.startswith("\"") and service_binary_path.endswith("\""))',
    mitre_techniques=["T1543.003"],
    evidence_requirements=["service_binary_path", "service_name", "service_display_name"],
    investigation_guidance="Check if the service binary path is properly quoted. Unquoted paths with spaces can be exploited for hijacking. Verify the service binary location.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Some legacy services may have unquoted paths without issues.",
    suppression_expiry=None,
)

# --- Rule: Writable Service Binary Detection ---

WRITABLE_SERVICE_BINARY = DetectionRule(
    rule_id="SV-002",
    rule_name="Writable Service Binary Detection",
    description="Detects services with binaries that have write permissions for non-admin users",
    category="service",
    severity="medium",
    confidence=65.0,
    condition="service_binary_path and service_binary_is_writable_by_non_admin",
    mitre_techniques=["T1543.003"],
    evidence_requirements=["service_binary_path", "service_binary_permissions"],
    investigation_guidance="Check service binary file permissions. If writable by non-admin users, this could allow service modification by standard users.",
    version=1,
    enabled=True,
    false_positive_rate=0.10,
    false_positive_justification="Some services legitimately have writable binaries for dynamic loading.",
    suppression_expiry=None,
)

# --- Rule: Writable Service Directory Detection ---

WRITABLE_SERVICE_DIR = DetectionRule(
    rule_id="SV-003",
    rule_name="Writable Service Directory Detection",
    description="Detects services with binaries in directories that are writable by non-admin users",
    category="service",
    severity="medium",
    confidence=60.0,
    condition="service_binary_directory and directory_is_writable_by_non_admin",
    mitre_techniques=["T1543.003"],
    evidence_requirements=["service_binary_path", "service_binary_directory", "directory_permissions"],
    investigation_guidance="Check the directory containing the service binary. If writable by non-admin users, this could allow service binary replacement.",
    version=1,
    enabled=True,
    false_positive_rate=0.12,
    false_positive_justification="Some services legitimately require write access to their directories.",
    suppression_expiry=None,
)

# --- Rule: Unexpected Service Installation ---

UNEXPECTED_SERVICE_INSTALL = DetectionRule(
    rule_id="SV-004",
    rule_name="Unexpected Service Installation",
    description="Detects newly installed services that may indicate persistence or privilege escalation",
    category="service",
    severity="high",
    confidence=75.0,
    condition="new_service_detected and service_name not in known_services",
    mitre_techniques=["T1543.003"],
    evidence_requirements=["service_name", "service_display_name", "service_binary_path", "service_start_type"],
    investigation_guidance="Check if the newly installed service is expected. Look for services with names similar to legitimate services but in unusual locations. Check the service binary path and start type.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="New services may be installed by legitimate software updates or admin tools.",
    suppression_expiry=None,
)

# --- Rule: Suspicious Service Account Configuration ---

SUSPICIOUS_SERVICE_ACCOUNT = DetectionRule(
    rule_id="SV-005",
    rule_name="Suspicious Service Account Configuration",
    description="Detects services running with unusual or high-privilege accounts",
    category="service",
    severity="high",
    confidence=70.0,
    condition='service_account not in ["LocalSystem", "NetworkService", "LocalService"] and not service_account.matches(r"^[A-Za-z]{1,2}\\\\.[A-Za-z]{1,}")',
    mitre_techniques=["T1543.003"],
    evidence_requirements=["service_account", "service_name", "service_display_name"],
    investigation_guidance="Check if the service account is expected. Service accounts should typically be LocalSystem, NetworkService, or a dedicated domain account. Unusual accounts may indicate privilege escalation or persistence.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Some applications require specific service accounts to function.",
    suppression_expiry=None,
)

# --- Rule: Lookalike Process Name Detection ---

LOOKALIKE_PROCESS_NAME = DetectionRule(
    rule_id="PR-001",
    rule_name="Lookalike Process Name Detection",
    description="Detects processes with names similar to legitimate Windows system processes",
    category="process",
    severity="medium",
    confidence=65.0,
    condition='process_name in ["sihost.exe", "svch0st.exe", "explore.exe", "csrss.exe", "lsass.exe", "services.exe", "winlogon.exe"] and process_exe not in expected_paths',
    mitre_techniques=["T1036.005"],
    evidence_requirements=["process_name", "process_exe", "process_pid", "process_ppid"],
    investigation_guidance="Check if the process name is a lookalike of a legitimate system process. Verify the executable path and parent process. Legitimate system processes run from specific locations.",
    version=1,
    enabled=True,
    false_positive_rate=0.20,
    false_positive_justification="Some legitimate applications may use similar names.",
    suppression_expiry=None,
)

# --- Rule: Office Applications Spawning Script Interpreters ---

OFFICE_SPAWNING_SCRIPT = DetectionRule(
    rule_id="PR-002",
    rule_name="Office Application Spawning Script Interpreter",
    description="Detects Office applications (Word, Excel, PowerPoint) spawning script interpreters",
    category="process",
    severity="high",
    confidence=85.0,
    condition='parent_process_name in ["WINWORD.EXE", "EXCEL.EXE", "POWERPNT.EXE", "OUTLOOK.EXE", "MSACCESS.EXE"] and process_name in ["cmd.exe", "powershell.exe", "wscript.exe", "cscript.exe", "mshta.exe", "regsvr32.exe", "rundll32.exe"]',
    mitre_techniques=["T1059.001", "T1059.005"],
    evidence_requirements=["process_name", "parent_process_name", "process_cmdline", "process_pid", "parent_pid"],
    investigation_guidance="Office applications should not spawn script interpreters. This is a common technique for macro-based malware execution. Check the command line and any downloaded files.",
    version=1,
    enabled=True,
    false_positive_rate=0.05,
    false_positive_justification="Legitimate add-ins or automation may occasionally spawn scripts.",
    suppression_expiry=None,
)

# --- Rule: Unexpected Script Interpreter Execution ---

UNEXPECTED_SCRIPT_INTERPRETER = DetectionRule(
    rule_id="PR-003",
    rule_name="Unexpected Script Interpreter Execution",
    description="Detects unexpected execution of script interpreters from unusual locations or contexts",
    category="process",
    severity="medium",
    confidence=60.0,
    condition='process_name in ["powershell.exe", "wscript.exe", "cscript.exe", "mshta.exe"] and process_exe not in ["C:\\Windows\\System32\\", "C:\\Windows\\SysWOW64\\"]',
    mitre_techniques=["T1059.001", "T1059.003", "T1059.005"],
    evidence_requirements=["process_name", "process_exe", "process_cmdline", "process_username"],
    investigation_guidance="Script interpreters should typically run from System32 or SysWOW64. Execution from temp directories, user profiles, or network shares is suspicious.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Some legitimate software may bundle interpreters or run scripts from non-standard locations.",
    suppression_expiry=None,
)

# --- Rule: Executable in Unusual Directory ---

EXECUTABLE_IN_UNUSUAL_DIR = DetectionRule(
    rule_id="PR-004",
    rule_name="Executable in Unusual Directory",
    description="Detects executables running from unusual directories (temp, appdata, downloads, etc.)",
    category="process",
    severity="medium",
    confidence=60.0,
    condition='process_exe matches regex "(?i)(temp|tmp|appdata|downloads|programdata|users\\\\(desktop|documents|pictures|music|videos))"',
    mitre_techniques=["T1059", "T1204"],
    evidence_requirements=["process_exe", "process_name", "process_cmdline", "process_pid"],
    investigation_guidance="Executables running from user-writable directories are often malware or unauthorized software. Verify the file hash and origin.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Some legitimate portable applications run from user directories.",
    suppression_expiry=None,
)

# --- Rule: Suspicious Temporary Directory Execution ---

SUSPICIOUS_TEMP_EXECUTION = DetectionRule(
    rule_id="PR-005",
    rule_name="Suspicious Temporary Directory Execution",
    description="Detects executables running from temporary directories",
    category="process",
    severity="high",
    confidence=80.0,
    condition='process_exe matches regex "(?i)(temp|tmp)\\\\" and process_name not in ["installer.exe", "setup.exe", "update.exe"]',
    mitre_techniques=["T1059", "T1204"],
    evidence_requirements=["process_exe", "process_name", "process_cmdline", "process_pid"],
    investigation_guidance="Execution from temp directories is a common malware technique. Check the file hash, parent process, and any network connections.",
    version=1,
    enabled=True,
    false_positive_rate=0.10,
    false_positive_justification="Legitimate installers and updaters may run from temp directories.",
    suppression_expiry=None,
)

# --- Rule: Unsigned Executable Anomalies ---

UNSIGNED_EXECUTABLE_ANOMALY = DetectionRule(
    rule_id="PR-006",
    rule_name="Unsigned Executable Anomaly",
    description="Detects unsigned executables running in sensitive contexts",
    category="process",
    severity="medium",
    confidence=55.0,
    condition='not process_signature.is_signed and (process_username in ["SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE"] or process_integrity_level in ["High", "System"])',
    mitre_techniques=["T1055", "T1036"],
    evidence_requirements=["process_exe", "process_signature", "process_username", "process_integrity_level"],
    investigation_guidance="Unsigned executables running with high privileges are suspicious. Check the file origin, hash reputation, and parent process.",
    version=1,
    enabled=True,
    false_positive_rate=0.20,
    false_positive_justification="Many legitimate internal tools and legacy applications are unsigned.",
    suppression_expiry=None,
)

# --- Rule: Unexpected Privileged Process ---

UNEXPECTED_PRIVILEGED_PROCESS = DetectionRule(
    rule_id="PR-007",
    rule_name="Unexpected Privileged Process",
    description="Detects unexpected processes running with high integrity levels",
    category="process",
    severity="high",
    confidence=75.0,
    condition='process_integrity_level in ["High", "System"] and process_name not in expected_system_processes',
    mitre_techniques=["T1055", "T1068"],
    evidence_requirements=["process_name", "process_exe", "process_integrity_level", "process_username", "process_pid"],
    investigation_guidance="Processes running with High or System integrity should be well-known system processes. Unexpected processes at this level may indicate privilege escalation.",
    version=1,
    enabled=True,
    false_positive_rate=0.10,
    false_positive_justification="Some legitimate administrative tools run with elevated privileges.",
    suppression_expiry=None,
)

# --- Rule: Suspicious Command Line Patterns ---

SUSPICIOUS_COMMAND_LINE = DetectionRule(
    rule_id="PR-008",
    rule_name="Suspicious Command Line Patterns",
    description="Detects suspicious command line patterns commonly used in attacks",
    category="process",
    severity="high",
    confidence=80.0,
    condition='process_cmdline matches regex "(?i)(-enc|--encoded|-nop|--noninteractive|bypass|-w hidden|downloadstring|invoke-expression|iex|frombase64|iex|powershell.*-e|certutil.*-decode|regsvr32.*scrobj|rundll32.*javascript|mshta.*javascript)"',
    mitre_techniques=["T1059.001", "T1027", "T1218"],
    evidence_requirements=["process_cmdline", "process_name", "process_pid", "process_username"],
    investigation_guidance="These command line patterns are commonly used in obfuscated payloads and living-off-the-land attacks. Review the full command line and parent process.",
    version=1,
    enabled=True,
    false_positive_rate=0.10,
    false_positive_justification="Legitimate administrative scripts may use some of these patterns.",
    suppression_expiry=None,
)

# --- Rule: Process Baseline Deviation ---

PROCESS_BASELINE_DEVIATION = DetectionRule(
    rule_id="PR-009",
    rule_name="Process Baseline Deviation",
    description="Detects processes that deviate from established baselines (execution time, frequency, user context)",
    category="process",
    severity="medium",
    confidence=50.0,
    condition='process_name in known_processes and (execution_time outside expected_window or user_context != expected_user or frequency > expected_frequency)',
    mitre_techniques=["T1059", "T1053"],
    evidence_requirements=["process_name", "process_username", "create_time", "execution_history"],
    investigation_guidance="Processes that deviate from historical baselines may indicate account compromise or unauthorized activity. Review the execution pattern and user context.",
    version=1,
    enabled=True,
    false_positive_rate=0.25,
    false_positive_justification="Baselines may not capture all legitimate variations in process behavior.",
    suppression_expiry=None,
)

# --- Rule: Unexpected Process Execution ---

UNEXPECTED_PROCESS_EXECUTION = DetectionRule(
    rule_id="PR-010",
    rule_name="Unexpected Process Execution",
    description="Detects processes that are unexpected in the current environment context",
    category="process",
    severity="medium",
    confidence=55.0,
    condition='process_name not in environment_baseline and not process_name in allowed_processes',
    mitre_techniques=["T1059"],
    evidence_requirements=["process_name", "process_exe", "process_cmdline", "process_username", "process_pid"],
    investigation_guidance="Processes not in the environment baseline may indicate unauthorized software or lateral movement. Verify the executable hash and origin.",
    version=1,
    enabled=True,
    false_positive_rate=0.20,
    false_positive_justification="New legitimate software may not be in the baseline yet.",
    suppression_expiry=None,
)

# --- Startup Detection Rules ---

STARTUP_UNEXPECTED_ENTRY = DetectionRule(
    rule_id="ST-001",
    rule_name="Unexpected Startup Entry",
    description="Detects unexpected entries in startup locations",
    category="startup",
    severity="high",
    confidence=80.0,
    condition='startup_entry not in known_startup_entries and startup_source in ["registry_run", "registry_runonce", "startup_folder", "scheduled_task"]',
    mitre_techniques=["T1547.001", "T1053.005"],
    evidence_requirements=["startup_source", "startup_name", "startup_command", "startup_user_context"],
    investigation_guidance="Review the new startup entry. Check the executable path, command line, and whether it matches legitimate software. Persistence mechanisms are commonly added to startup locations.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Legitimate software installations may add startup entries.",
    suppression_expiry=None,
)

STARTUP_NEW_ENTRY = DetectionRule(
    rule_id="ST-002",
    rule_name="New Startup Entry Detected",
    description="Detects new startup entries since last collection",
    category="startup",
    severity="medium",
    confidence=70.0,
    condition="new_startup_entry_detected",
    mitre_techniques=["T1547.001", "T1053.005"],
    evidence_requirements=["startup_source", "startup_name", "startup_command", "startup_user_context"],
    investigation_guidance="Review the new startup entry. Verify it corresponds to a recent legitimate software installation or update.",
    version=1,
    enabled=True,
    false_positive_rate=0.20,
    false_positive_justification="New legitimate software often adds startup entries.",
    suppression_expiry=None,
)

STARTUP_PATH_ANOMALY = DetectionRule(
    rule_id="ST-003",
    rule_name="Startup Path Anomaly",
    description="Detects startup entries with anomalous paths",
    category="startup",
    severity="medium",
    confidence=65.0,
    condition='startup_executable_path matches regex "(?i)(temp|tmp|appdata|downloads|programdata|recycle)"',
    mitre_techniques=["T1547.001", "T1053.005"],
    evidence_requirements=["startup_executable_path", "startup_command", "startup_source"],
    investigation_guidance="Startup entries pointing to temporary or user-writable directories are highly suspicious. Verify the executable and its origin.",
    version=1,
    enabled=True,
    false_positive_rate=0.10,
    false_positive_justification="Some portable applications may run from user directories.",
    suppression_expiry=None,
)

STARTUP_BASELINE_DEVIATION = DetectionRule(
    rule_id="ST-004",
    rule_name="Startup Baseline Deviation",
    description="Detects deviations from startup inventory baseline",
    category="startup",
    severity="medium",
    confidence=55.0,
    condition='startup_entry_count > baseline_count * 1.5 or new_persistence_mechanism_detected',
    mitre_techniques=["T1547", "T1053"],
    evidence_requirements=["startup_entries", "baseline_count", "changes_since_last_collection"],
    investigation_guidance="Significant increases in startup entries or new persistence mechanisms may indicate systematic compromise.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Legitimate software installations and updates change startup inventory.",
    suppression_expiry=None,
)

SUSPICIOUS_SCHEDULED_TASK = DetectionRule(
    rule_id="ST-005",
    rule_name="Suspicious Scheduled Task Configuration",
    description="Detects scheduled tasks with suspicious configurations",
    category="startup",
    severity="high",
    confidence=75.0,
    condition='task_action_executable matches regex "(?i)(powershell|cmd|wscript|cscript|mshta|regsvr32|rundll32)" and task_trigger_type in ["on_idle", "on_logon", "at_startup"]',
    mitre_techniques=["T1053.005"],
    evidence_requirements=["task_name", "task_action_executable", "task_arguments", "task_trigger_type", "task_user_context"],
    investigation_guidance="Scheduled tasks running script interpreters or system utilities with persistence triggers are commonly used for malware persistence.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Legitimate administrative tasks may use these patterns.",
    suppression_expiry=None,
)

UNUSUAL_AUTO_START_SERVICE = DetectionRule(
    rule_id="ST-006",
    rule_name="Unusual Automatic-Start Service",
    description="Detects services set to auto-start that are unusual or unexpected",
    category="startup",
    severity="medium",
    confidence=60.0,
    condition='service_start_type == "auto" and service_name not in expected_auto_start_services',
    mitre_techniques=["T1543.003"],
    evidence_requirements=["service_name", "service_display_name", "service_start_type", "service_binary_path"],
    investigation_guidance="Auto-start services that are not part of the expected baseline may indicate persistence. Verify the service purpose and binary.",
    version=1,
    enabled=True,
    false_positive_rate=0.15,
    false_positive_justification="Some legitimate software installs auto-start services.",
    suppression_expiry=None,
)

# --- Event Correlation Rules ---

CORRELATION_PROCESS_SERVICE = DetectionRule(
    rule_id="CR-001",
    rule_name="Process-Service Correlation",
    description="Correlates process creation with service installation events",
    category="correlation",
    severity="high",
    confidence=75.0,
    condition="service_install_event and related_process_creation within 300 seconds",
    mitre_techniques=["T1543.003", "T1055"],
    evidence_requirements=["service_install_event", "process_creation_event", "time_delta"],
    investigation_guidance="A service installation followed by related process creation may indicate malware installing persistence and immediately executing.",
    version=1,
    enabled=True,
    false_positive_rate=0.10,
    false_positive_justification="Legitimate software installers may create services and launch processes.",
    suppression_expiry=None,
)

CORRELATION_LOGON_PROCESS = DetectionRule(
    rule_id="CR-002",
    rule_name="Logon-Process Correlation",
    description="Correlates successful logons with subsequent suspicious process execution",
    category="correlation",
    severity="medium",
    confidence=60.0,
    condition="logon_event (4624) and suspicious_process_creation within 600 seconds by same user",
    mitre_techniques=["T1059", "T1556"],
    evidence_requirements=["logon_event", "process_creation_event", "user_sid", "time_delta"],
    investigation_guidance="A successful logon followed by suspicious process execution may indicate post-exploitation activity.",
    version=1,
    enabled=True,
    false_positive_rate=0.20,
    false_positive_justification="Legitimate user activity after logon may trigger this correlation.",
    suppression_expiry=None,
)

# All rules grouped for easy loading
ALL_SERVICE_RULES = [
    UNQUOTED_SERVICE_PATH,
    WRITABLE_SERVICE_BINARY,
    WRITABLE_SERVICE_DIR,
    UNEXPECTED_SERVICE_INSTALL,
    SUSPICIOUS_SERVICE_ACCOUNT,
]

ALL_PROCESS_RULES = [
    LOOKALIKE_PROCESS_NAME,
    OFFICE_SPAWNING_SCRIPT,
    UNEXPECTED_SCRIPT_INTERPRETER,
    EXECUTABLE_IN_UNUSUAL_DIR,
    SUSPICIOUS_TEMP_EXECUTION,
    UNSIGNED_EXECUTABLE_ANOMALY,
    UNEXPECTED_PRIVILEGED_PROCESS,
    SUSPICIOUS_COMMAND_LINE,
    PROCESS_BASELINE_DEVIATION,
    UNEXPECTED_PROCESS_EXECUTION,
]

ALL_STARTUP_RULES = [
    STARTUP_UNEXPECTED_ENTRY,
    STARTUP_NEW_ENTRY,
    STARTUP_PATH_ANOMALY,
    STARTUP_BASELINE_DEVIATION,
    SUSPICIOUS_SCHEDULED_TASK,
    UNUSUAL_AUTO_START_SERVICE,
]

ALL_CORRELATION_RULES = [
    CORRELATION_PROCESS_SERVICE,
    CORRELATION_LOGON_PROCESS,
]

ALL_RULES = ALL_SERVICE_RULES + ALL_PROCESS_RULES + ALL_STARTUP_RULES + ALL_CORRELATION_RULES
