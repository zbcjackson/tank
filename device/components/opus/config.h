/* libopus 1.4 build configuration for ESP32-S3 (fixed-point).
 * Mirrors the configure.ac defaults for an embedded fixed-point build. */
#define OPUS_BUILD 1
#define FIXED_POINT 1
#define VAR_ARRAYS 1              /* C99 VLAs — exactly one of VAR_ARRAYS /
                                     USE_ALLOCA / NONTHREADSAFE_PSEUDOSTACK */
#define HAVE_LRINT 1
#define HAVE_LRINTF 1
#define PACKAGE_VERSION "1.4.0"
/* #define ENABLE_ASSERTIONS */  /* off */
/* #define CUSTOM_MODES */        /* off — smaller flash */
