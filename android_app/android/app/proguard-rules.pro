# The JNI functions in libjetlink.so are found by name.
-keep class io.zoompilot.jetlink.server.Native { *; }
# kotlinx.serialization keeps what its plugin generates.
-keepattributes *Annotation*, InnerClasses
