package com.hidra

/**
 * What the keyboard UI is allowed to know about how keys leave the phone.
 *
 * The UI calls down/up/releaseAll and reads `status`; it never learns whether that becomes a
 * Bluetooth HID report, a WebSocket line to an ESP32, or nothing at all. Phase 2 hangs the
 * WebView off this and Phase 4 can swap the UI without touching anything below it.
 */
interface KeyTransport {

    /** Begin trying to be a keyboard. Idempotent. */
    fun start()

    /** Stop, releasing any held keys first so nothing is left stuck on the far end. */
    fun stop()

    fun keyDown(usage: Int)
    fun keyUp(usage: Int)
    fun releaseAll()

    val status: LinkStatus

    /** Called on the main thread whenever [status] changes. */
    var onStatus: ((LinkStatus) -> Unit)?

    /** Optional human-readable trace, for the diagnostics panel. */
    var onLog: ((String) -> Unit)?
}

enum class LinkState {
    /** Not started, or stopped. */
    STOPPED,

    /** Starting up, or recovering — obtaining the profile proxy / registering. */
    STARTING,

    /** Advertising as a keyboard, but no device has connected yet. */
    READY,

    /** A device is connected but has not yet accepted us as its keyboard. */
    CONNECTING,

    /** A device is connected. This is the only state in which keys go anywhere. */
    CONNECTED,

    /** Something is wrong that the user needs to act on — see [LinkStatus.detail]. */
    FAILED
}

/**
 * `canType` exists so the UI can never present a control that silently does nothing — the
 * lesson from Phase 0, where registration expired unnoticed and every connect attempt failed
 * without a word (spike/RESULTS.md §T1b).
 */
data class LinkStatus(
    val state: LinkState,
    val hostName: String? = null,
    val detail: String? = null
) {
    val canType get() = state == LinkState.CONNECTED

    fun describe(): String = when (state) {
        LinkState.STOPPED -> "stopped"
        LinkState.STARTING -> detail ?: "starting…"
        LinkState.READY -> "ready — connect to HIDRA from the other device"
        LinkState.CONNECTING -> "${hostName ?: "device"} connected, accepting the keyboard…"
        LinkState.CONNECTED -> "typing to ${hostName ?: "device"}"
        LinkState.FAILED -> detail ?: "failed"
    }
}
