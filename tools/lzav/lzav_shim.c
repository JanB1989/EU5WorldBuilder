#include "lzav.h"

int wb_lzav_bound(int srclen) { return lzav_compress_bound_hi(srclen); }

int wb_lzav_compress(const void* src, void* dst, int srclen, int dstlen)
{
	return lzav_compress_hi(src, dst, srclen, dstlen);
}

int wb_lzav_decompress(const void* src, void* dst, int srclen, int dstlen)
{
	return lzav_decompress(src, dst, srclen, dstlen);
}
