"""Value catalogs and distribution weights derived from GEH sample_data."""

from __future__ import annotations

from .models import SiteProfile, SystemProfile

DEFAULT_SITE = SiteProfile()

SYSTEMS: dict[str, SystemProfile] = {
    "CTBAY47": SystemProfile(
        sysid="CTBAY47",
        product_name="Revolution Apex Elite (160)",
        systype="Revolution Apex",
        sw_version="25MW38.54",
    ),
    "CTBAY51WSO": SystemProfile(
        sysid="CTBAY51WSO",
        product_name="Revolution CT (Rev 160)",
        systype="Revolution CT",
        sw_version="25MW38.52",
    ),
    "CTBAY52WSO": SystemProfile(
        sysid="CTBAY52WSO",
        product_name="Revolution CT (Rev 160)",
        systype="Revolution CT",
        sw_version="25MW38.50",
    ),
    "CTBAY56WSO": SystemProfile(
        sysid="CTBAY56WSO",
        product_name="Revolution CT (Rev 160)",
        systype="Revolution CT",
        sw_version="25MW38.54",
    ),
    "CTBAY57WSO": SystemProfile(
        sysid="CTBAY57WSO",
        product_name="Revolution CT (Rev 160)",
        systype="Revolution CT",
        sw_version="25MW27.33",
    ),
    "CTBAY58": SystemProfile(
        sysid="CTBAY58",
        product_name="Revolution Apex Elite (160)",
        systype="Revolution Apex",
        sw_version="24MW10.61",
    ),
}

# Relative volume by sysid from sample (normalized later).
SYSTEM_WEIGHTS: dict[str, float] = {
    "CTBAY47": 903,
    "CTBAY51WSO": 548,
    "CTBAY56WSO": 414,
    "CTBAY57WSO": 405,
    "CTBAY52WSO": 291,
    "CTBAY58": 147,
}

ANATOMY_WEIGHTS: dict[str, float] = {
    "Orbit": 516,
    "Head": 304,
    "Abdomen": 197,
    "Chest": 181,
    "Recently Scanned": 165,
    "Service": 129,
    "Spine": 125,
    "Lower Extremity": 31,
    "Upper Extremity": 28,
    "Pelvis": 19,
    "Miscellaneous": 10,
    "Neck": 9,
}

PROTOCOLS: list[tuple[str, str, str]] = [
    # (protocol_category, ifr_event_protocol_name, anatomy_hint)
    ("21", "21.1 CT HEAD", "Head"),
    ("27", "27.1 CT L SPINE Helical SmartFlux 80mm", "Spine"),
    ("61", "61.1 CT Pluto Axial", "Orbit"),
    ("6", "6.1 PolyTrauma Digital 5.0 M2", "Chest"),
    ("41", "41.2 Service_Generic_Scan", "Service"),
    ("2", "2.31 SQUISH_SYS_BLUEGAMMEX_6309_Pluto_80mm", "Orbit"),
    ("2", "2.5 SQUISH_SYS_12.5WATER_4472_Pluto_80mm", "Orbit"),
    ("5", "5.2 Multi-Phase_Cardiac", "Chest"),
    ("25", "25.1 Abdomen Helical", "Abdomen"),
    ("1", "1.1 CT Soft Tissue Neck", "Neck"),
]

# Fixed severity for event types that are constant in the sample.
FIXED_SEVERITY: dict[str, str] = {
    "Exam_start": "Informational",
    "Exam_end": "Informational",
    "start_patient_session": "Informational",
    "gantry_subsystems_reseting": "Informational",
    "gantry_subsystem_ready": "Informational",
    "scanning_system_abort": "Informational",
    "start_of_calibration": "Informational",
    "operator_paused_scan": "Informational",
    "operator_aborted_scan": "Informational",
    "Timing Bolus": "Informational",
    "scan_failure": "N/A",
    "detectorcontrol_ack_packet_receive": "N/A",
    "stu_compute_calculation_error": "N/A",
    "scansetup_failure": "N/A",
    "scanhardware_down": "N/A",
    "recon_failure": "N/A",
    "failed_qc_recon_job": "N/A",
}

# Conditional severity weights from sample.
SEVERITY_WEIGHTS: dict[str, dict[str, float]] = {
    "reli_error_code": {
        "Critical": 0.696,
        "Warning": 0.199,
        "Informational": 0.083,
        "N/A": 0.021,
    },
    "ifr_error_code": {
        "N/A": 0.562,
        "Warning": 0.390,
        "Informational": 0.035,
        "Critical": 0.013,
    },
}

MESSAGES: dict[str, list[str]] = {
    "Exam_start": ["Study Start: Prospective Exam: {exam} : Protocol: {protocol_short}"],
    "Exam_end": ["Study End: Prospective Exam: {exam} : Protocol: {protocol_short}"],
    "start_patient_session": [
        "E{exam},SESSION_TYPE :SCAN_SESSION , {protocol_short} : EN: {exam}, PN: {protocol}, SN: Scout"
    ],
    "reli_error_code": [
        "Creating DICOM association failed",
        "Host : Gantry Control Board    Ermes # : 600030005 Exception Class : Abort    Severity : Primary",
        "Host : Gantry Control Board    Ermes # : 260116313 Exception Class : Safe State    Severity : Primary",
    ],
    "ifr_error_code": [
        "The System Software has terminated.",
        "Scout image not available",
        "Host : Gantry Control Board    Ermes # : 260116313 Exception Class : Safe State    Severity : Primary File : subsys_mgr.",
    ],
    "detectorcontrol_ack_packet_receive": [
        "Host : Data Chain Board    Ermes # : 1100203000 Exception Class : Soft    Severity : Sec/Soft File : DetectorDriverAccess"
    ],
    "gantry_subsystems_reseting": [
        "Performing HARD RESET through serial connection ...."
    ],
    "gantry_subsystem_ready": [
        "Scanning hardware reset successful (1).",
        "Scanning hardware reset successful (0).",
    ],
    "scan_failure": [
        "Function: System Control : Scan Control  Scan Type: Scout Scan: {exam}/1/1  Scan Seq Id: 44000 Scan was Paused/Aborted by Fault"
    ],
    "scanning_system_abort": [
        "Function: System Control : Scan Control  Scan Type: Axial Scan: {exam}/2/1  Scan Seq Id: 5000 Scanning System Aborted Scan"
    ],
    "start_of_calibration": [
        "UpdateCalibration",
        "Uniformity Calibration",
        "AutoCombinedDetailedCal is started",
    ],
    "stu_compute_calculation_error": ["STU compute calculation error"],
    "scansetup_failure": ["Scan setup failure"],
    "scanhardware_down": ["Scan hardware down"],
    "operator_paused_scan": ["Operator paused scan"],
    "recon_failure": ["Reconstruction failure"],
    "failed_qc_recon_job": ["Failed QC recon job"],
    "operator_aborted_scan": ["Operator aborted scan"],
    "landmark_not_set": ["Landmark not set"],
    "component_configuration_timeout": ["Component configuration timeout"],
    "estop_activated": ["E-stop activated"],
    "dts_communication_lost": [
        "Host : Detector Control Board    Ermes # : 1000023033 Exception Class : Soft    DTS has lost stable communication"
    ],
    "detector_link_data_error": ["Detector link data error"],
    "session_crash": ["Session crash"],
    "system_software_error": ["System software error"],
}

IFR_EVENT_NAMES: dict[str, str] = {
    "Exam_start": "EXAMSTART",
    "Exam_end": "EXAMEND",
    "start_patient_session": "Start patient session",
    "detectorcontrol_ack_packet_receive": "Detector ack packet receive fail",
    "gantry_subsystems_reseting": "Gantry subsystems reseting",
    "gantry_subsystem_ready": "Gantry subsystem ready",
    "reli_error_code": "ian dicom association error",
    "ifr_error_code": "System software shut down",
    "scan_failure": "Scan failure",
    "scanning_system_abort": "Scanning system abort",
    "start_of_calibration": "Start of calibration",
}

# Intra-exam collateral events and relative odds (given an exam is running).
EXAM_COLLATERAL_WEIGHTS: dict[str, float] = {
    "reli_error_code": 0.28,
    "ifr_error_code": 0.26,
    "detectorcontrol_ack_packet_receive": 0.12,
    "gantry_subsystems_reseting": 0.08,
    "gantry_subsystem_ready": 0.06,
    "scan_failure": 0.06,
    "scanning_system_abort": 0.05,
    "start_of_calibration": 0.03,
    "stu_compute_calculation_error": 0.02,
    "scansetup_failure": 0.015,
    "scanhardware_down": 0.012,
    "operator_paused_scan": 0.01,
    "recon_failure": 0.008,
    "failed_qc_recon_job": 0.005,
    "operator_aborted_scan": 0.004,
    "landmark_not_set": 0.003,
    "dts_communication_lost": 0.002,
    "detector_link_data_error": 0.002,
    "estop_activated": 0.002,
    "session_crash": 0.001,
    "system_software_error": 0.001,
}
