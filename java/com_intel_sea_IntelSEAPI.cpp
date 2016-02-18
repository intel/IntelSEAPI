#include "java/com_intel_sea_IntelSEAPI.h"
#include "ittnotify.h"

extern "C" {
    JNIEXPORT jlong JNICALL Java_com_intel_sea_IntelSEAPI_createDomain(JNIEnv* pEnv, jclass, jstring name)
    {
        const char * nativeString = pEnv->GetStringUTFChars(name, nullptr);
        if (!nativeString) return 0;
        __itt_domain* pDomain = __itt_domain_create(nativeString);
        pEnv->ReleaseStringUTFChars(name, nativeString);
        return (jlong)pDomain;
    }

    JNIEXPORT jlong JNICALL Java_com_intel_sea_IntelSEAPI_createString(JNIEnv * pEnv, jclass, jstring name)
    {
        const char * nativeString = pEnv->GetStringUTFChars(name, nullptr);
        if (!nativeString) return 0;
        __itt_string_handle* pString = __itt_string_handle_create(nativeString);
        pEnv->ReleaseStringUTFChars(name, nativeString);
        return (jlong)pString;
    }

    JNIEXPORT void JNICALL Java_com_intel_sea_IntelSEAPI_beginTask(JNIEnv * pEnv, jclass, jlong domain, jlong name, jlong id, jlong parent, jlong timestamp)
    {
        __itt_task_begin_ex(
            reinterpret_cast<__itt_domain*>(domain),
            nullptr,
            timestamp,
            id ? __itt_id_make((void*)domain, id) : __itt_null,
            parent ? __itt_id_make((void*)domain, parent) : __itt_null,
            reinterpret_cast<__itt_string_handle*>(name)
        );
    }

    JNIEXPORT void JNICALL Java_com_intel_sea_IntelSEAPI_endTask(JNIEnv *, jclass, jlong domain, jlong timestamp)
    {
        __itt_task_end_ex(
            reinterpret_cast<__itt_domain*>(domain),
            nullptr,
            timestamp
        );
    }

    JNIEXPORT jlong JNICALL Java_com_intel_sea_IntelSEAPI_counterCreate(JNIEnv *, jclass, jlong domain, jlong name)
    {
        __itt_counter conuter = __itt_counter_create_typed(
            reinterpret_cast<__itt_string_handle*>(name)->strA,
            reinterpret_cast<__itt_domain*>(domain)->nameA,
            __itt_metadata_double
        );
        return (jlong)conuter;
    }

    JNIEXPORT void JNICALL Java_com_intel_sea_IntelSEAPI_setCounter(JNIEnv *, jclass, jlong counter, jdouble value, jlong timestamp)
    {
        __itt_counter_set_value_ex(reinterpret_cast<__itt_counter>(counter), nullptr, timestamp, &value);
    }

    JNIEXPORT void JNICALL Java_com_intel_sea_IntelSEAPI_marker(JNIEnv *, jclass, jlong domain, jlong id, jlong name, jlong scope, jlong timestamp)
    {
        __itt_marker_ex(
            reinterpret_cast<__itt_domain*>(domain),
            nullptr, //zero clock domain means that given time is already a correct timestamp
            timestamp,
            id ? __itt_id_make((void*)domain, id) : __itt_null,
            reinterpret_cast<__itt_string_handle*>(name),
            (__itt_scope)scope
        );
    }

    JNIEXPORT jlong JNICALL Java_com_intel_sea_IntelSEAPI_createTrack(JNIEnv * pEnv, jclass, jstring group, jstring track)
    {
        const char * szGroup = group ? pEnv->GetStringUTFChars(group, nullptr) : nullptr;
        const char * szTrack = pEnv->GetStringUTFChars(track, nullptr);

        __itt_track* pTrack = __itt_track_create(
            __itt_track_group_create(((group) ? __itt_string_handle_create(szGroup) : nullptr), __itt_track_group_type_normal),
            __itt_string_handle_create(szTrack),
            __itt_track_type_normal
        );

        pEnv->ReleaseStringUTFChars(track, szTrack);
        if (group)
            pEnv->ReleaseStringUTFChars(group, szGroup);

        return (jlong)pTrack;
    }

    JNIEXPORT void JNICALL Java_com_intel_sea_IntelSEAPI_setTrack(JNIEnv *, jclass, jlong track)
    {
        __itt_set_track(reinterpret_cast<__itt_track*>(track));
    }

    JNIEXPORT jlong JNICALL Java_com_intel_sea_IntelSEAPI_getTimestamp(JNIEnv *, jclass)
    {
        return (jlong)__itt_get_timestamp();
    }
}
