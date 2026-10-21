"""Routes for OS Power Management and Shadow Background Execution."""

import os
import sys
import ctypes
import subprocess
import asyncio
import html
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

IS_MAC = sys.platform == "darwin"

router = APIRouter(prefix="/api/power", tags=["Power & Shadow"])

# Windows Execution State Flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

# In-memory state
_keep_awake_active = False
_pending_tasks = []
_caffeinate = None  # macOS: the `caffeinate` process that keeps the Mac awake


class ScheduleWakeRequest(BaseModel):
    delay_minutes: Optional[int] = None
    time_iso: Optional[str] = None
    task_name: Optional[str] = "AntigravityShadowTask"


class ShutdownRequest(BaseModel):
    delay_seconds: Optional[int] = 30
    action: Optional[str] = "shutdown"  # "shutdown", "sleep", "hibernate"
    message: Optional[str] = "Antigravity: Tareas de Shadow completadas. Apagando el equipo..."


class ShadowTask(BaseModel):
    id: str
    title: str
    prompt: str
    created_at: str
    status: str  # "queued", "running", "completed", "failed"
    auto_sleep_on_finish: bool = True


@router.get("/status")
async def get_power_status():
    """Returns the current power management and wake timer status."""
    is_windows = sys.platform == "win32"
    wake_timers_info = "Available"

    if is_windows:
        try:
            res = subprocess.run(
                ["powercfg", "/waketimers"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            wake_timers_info = res.stdout.strip() if res.stdout else "No active wake timers"
        except Exception:
            wake_timers_info = "Unable to query powercfg"
    elif IS_MAC:
        try:
            res = subprocess.run(["pmset", "-g", "sched"], capture_output=True, text=True, timeout=10)
            wake_timers_info = res.stdout.strip() or "No active wake timers"
        except Exception:
            wake_timers_info = "Unable to query pmset"

    return {
        "platform": sys.platform,
        "is_windows": is_windows,
        "keep_awake_active": _keep_awake_active,
        "away_mode_supported": is_windows or IS_MAC,
        "wake_timers": wake_timers_info,
        "queued_shadow_tasks": len(_pending_tasks),
    }


@router.post("/prevent-sleep")
async def prevent_sleep():
    """Enables Windows Away Mode / System Keep-Awake so tasks run without interruption."""
    global _keep_awake_active, _caffeinate
    if sys.platform == "win32":
        try:
            # Set Away Mode & System Required continuously
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
            _keep_awake_active = True
            return {"status": "ok", "message": "Away Mode enabled. System will remain active for tasks."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set execution state: {e}")
    elif IS_MAC:
        if _caffeinate is None or _caffeinate.poll() is not None:
            # -i: no idle sleep, -s: no system sleep on AC power, -w: ends by itself if the Bridge dies
            _caffeinate = subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])
        _keep_awake_active = True
        return {"status": "ok", "message": "caffeinate enabled. The Mac will remain awake for tasks."}
    else:
        _keep_awake_active = True
        return {"status": "ok", "message": "Keep-awake simulated for non-Windows platform."}


@router.post("/release-sleep")
async def release_sleep():
    """Releases Keep-Awake state, allowing normal system sleep."""
    global _keep_awake_active, _caffeinate
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            _keep_awake_active = False
            return {"status": "ok", "message": "Normal power state restored."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to reset execution state: {e}")
    elif IS_MAC:
        if _caffeinate is not None and _caffeinate.poll() is None:
            _caffeinate.terminate()
        _caffeinate = None
        _keep_awake_active = False
        return {"status": "ok", "message": "Normal power state restored."}
    else:
        _keep_awake_active = False
        return {"status": "ok", "message": "Released."}


@router.post("/sleep")
async def suspend_system():
    """Puts the computer into sleep / suspend mode."""
    if IS_MAC:
        try:
            subprocess.Popen(["pmset", "sleepnow"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"status": "ok", "message": "Sleep state initiated."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to sleep system: {e}")
    if sys.platform != "win32":
        return {"status": "mock", "message": "Sleep command is only executable on Windows."}

    try:
        # Run rundll32 powrprof.dll,SetSuspendState 0,1,0
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {"status": "ok", "message": "Sleep state initiated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sleep system: {e}")


@router.post("/shutdown")
async def shutdown_system(req: ShutdownRequest):
    """Shutting down or hibernating the computer is a hard limit of the Bridge: it is refused in every
    permission mode and cannot be switched on over HTTP (core/permissions.py). Use /api/power/sleep to suspend."""
    raise HTTPException(
        status_code=403,
        detail={
            "error": "blocked_by_policy",
            "message": "The Bridge never shuts down or hibernates the computer, in any permission mode. "
                       "Use /api/power/sleep to suspend it.",
        },
    )


@router.post("/cancel-shutdown")
async def cancel_shutdown():
    """Aborts a pending scheduled shutdown."""
    if sys.platform != "win32":
        return {"status": "mock", "message": "Shutdown cancellation is only on Windows."}

    try:
        res = subprocess.run(
            ["shutdown", "/a"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {"status": "ok", "message": "Shutdown cancelled.", "output": res.stdout.strip()}
    except Exception as e:
        return {"status": "error", "message": f"Failed or no shutdown was pending: {e}"}


@router.post("/schedule-wake")
async def schedule_wake(req: ScheduleWakeRequest):
    """Configures a Windows RTC Wake Alarm via PowerShell TaskScheduler (pmset on macOS)."""
    if IS_MAC:
        return await asyncio.to_thread(_schedule_wake_mac, req)
    if sys.platform != "win32":
        return {"status": "mock", "message": "Wake timers are only supported natively on Windows."}

    minutes = req.delay_minutes or 2
    task_name = req.task_name or "Antigravity_Shadow_Wake"

    # PowerShell command to create a Scheduled Task with WakeToRun enabled
    ps_script = f"""
    $triggerTime = (Get-Date).AddMinutes({minutes})
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c echo Antigravity Wake triggered at %TIME%"
    $trigger = New-ScheduledTaskTrigger -Once -At $triggerTime
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName "{task_name}" -Action $action -Trigger $trigger -Settings $settings -Force
    """

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return {
            "status": "ok",
            "message": f"Wake alarm programmed for +{minutes} minutes from now ({task_name}).",
            "task_name": task_name,
            "minutes": minutes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to program wake alarm: {e}")


def _schedule_wake_mac(req: ScheduleWakeRequest) -> dict:
    """`pmset schedule wake` needs root: it goes through the macOS admin prompt (osascript)."""
    from datetime import timedelta
    minutes = req.delay_minutes or 2
    when = (datetime.now() + timedelta(minutes=minutes)).strftime("%m/%d/%y %H:%M:%S")
    script = f'do shell script "pmset schedule wake \\"{when}\\"" with administrator privileges'
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Failed to program wake alarm: {res.stderr.strip()}")
    return {
        "status": "ok",
        "message": f"Wake alarm programmed for +{minutes} minutes from now (pmset).",
        "task_name": req.task_name or "Antigravity_Shadow_Wake",
        "minutes": minutes,
    }


class ToastNotificationRequest(BaseModel):
    title: Optional[str] = "Discord • #api-soporte"
    message: str
    app_id: Optional[str] = "Discord"
    duration_ms: Optional[int] = 3000


def _show_windows_toast_sync(title: str, message: str, app_id: str, duration_ms: int = 3000):
    safe_title = html.escape(title or "Discord • #api-soporte")
    safe_message = html.escape(message or "")
    raw_app_id = (app_id or "Discord").strip()

    if raw_app_id.lower() in ("discord", "discord.exe", "discord app", "com.squirrel.discord.discord"):
        target_aumid = "com.squirrel.Discord.Discord"
    elif raw_app_id.lower() in ("antigravity", "autotest"):
        target_aumid = "electron.app.Antigravity"
    else:
        target_aumid = raw_app_id

    duration_ms = max(500, int(duration_ms or 3000))

    # Resolve Discord icon path
    discord_icon_candidates = [
        os.path.expanduser(r"~\AppData\Local\Discord\discord_icon.png"),
        os.path.expanduser(r"~/.antigravity_bridge/discord_icon.png"),
        os.path.join(os.path.dirname(__file__), "discord_icon.png"),
    ]
    resolved_icon = ""
    for cand in discord_icon_candidates:
        if os.path.exists(cand):
            resolved_icon = os.path.abspath(cand).replace("\\", "/")
            break

    image_xml_node = f'<image placement="appLogoOverride" src="file:///{resolved_icon}"/>' if resolved_icon else ""

    ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast duration="short">
  <visual>
    <binding template="ToastGeneric">
      {image_xml_node}
      <text>{safe_title}</text>
      <text>{safe_message}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
$notifier = $null
try {{
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{target_aumid}")
    $notifier.Show($toast)
}} catch {{
    try {{
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("com.squirrel.Discord.Discord")
        $notifier.Show($toast)
    }} catch {{
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe")
        $notifier.Show($toast)
    }}
}}

if ($notifier) {{
    Start-Sleep -Milliseconds {duration_ms}
    try {{
        $notifier.Hide($toast)
    }} catch {{}}
}}
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=10,
        )
    except Exception as e:
        print(f"[PowerRouter] Error showing Windows toast: {e}")


@router.post("/toast")
@router.post("/notify")
async def trigger_toast(req: ToastNotificationRequest):
    """Triggers an OS-native Windows toast notification directly outside of the browser sandbox."""
    if IS_MAC:
        from core import macos
        asyncio.create_task(asyncio.to_thread(macos.notify, req.title or "Model Bridge", req.message))
        return {"status": "ok", "message": "Native macOS notification triggered."}
    if sys.platform != "win32":
        return {"status": "mock", "message": "Toast notifications are only supported natively on Windows."}

    duration = req.duration_ms if req.duration_ms is not None else 3000
    asyncio.create_task(asyncio.to_thread(_show_windows_toast_sync, req.title, req.message, req.app_id, duration))
    return {"status": "ok", "message": f"Native Windows toast triggered (auto-hide {duration}ms)."}

