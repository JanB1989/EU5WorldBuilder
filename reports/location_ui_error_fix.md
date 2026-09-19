# Location list underflow repair — 17 September 2026

The latest user-provided session log contains 649 copies of one message:
`pdx_gui_data_model.cpp:100: Trying to reshape data model with negative count -1`.
It contains no river-parser failures. The log does not name the emitting widget,
so attribution to a particular UI interaction is not established offline.

World Builder ships a copy of the native location window with a custom geography
strip. Its inherited list expressions skip fixed counts from possibly empty
estate, building and construction lists. Slot repeaters also use differences
that can become negative. Visibility conditions do not constrain these counts.
The generated window now bounds every top-level skip to the available list size
and every repeated-item count to zero or greater. Normal list ordering and slot
counts are unchanged. The native game installation is untouched.

Eleven bindings are guarded (five slices, six repeaters). Regression tests cover
empty/short/normal lists, negative and nonnegative counters, nested expressions,
comments, unaffected bindings and repeat generation. Both Min_int32 and Max_int32
are present in the installed EU5 executable; Min_int32 is also used by native GUI.

The build is synced to EU5 World Builder with full manifest byte parity. No game
was launched. The precise engine trigger and absence of this spam after the fix
remain for the user's next runtime check; offline tests cannot prove that no
other native screen can emit the same message.
