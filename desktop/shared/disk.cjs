// Room the apps always leave free on a drive they write to: a runtime that fills the system drive breaks the PC it
// runs on (a borrowed RTX 3060 on 2026-11-27 had 9.6 GB free on C:, and the Worker needed 7.7 GB there).
const FREE_SPACE_RESERVE_BYTES = 5 * 1024 ** 3;
/** True when `required` bytes fit in `free` and still leave the reserve. */
function leavesReserve(free, required, reserve = FREE_SPACE_RESERVE_BYTES) {
  return free >= required + reserve;
}
module.exports = { FREE_SPACE_RESERVE_BYTES, leavesReserve };
