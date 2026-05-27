# Import Dependencies

import subprocess
import os
from osgeo import gdal

# ── Configuration ─────────────────────────────────────────────
INPUT_DIR   = r"G:\Raster_Source"
OUTPUT_DIR  = r"G:\Raster_Source\Aligned_Raster"  # Auto_created OUTPUT folder
REF_DIR     = r"G:\Ref_Source\Reference_Raster.tif"  # Raster for emulating the extent and spatial resolution
REFERENCE   = None   # Set to r"G:\Ref_Source\Reference_Raster.tif" or leave None to auto-pick first raster in G:\Ref_Source
NODATA      = -9999
EPSG        = "EPSG:32646"  # Change to expected CRS
# ──────────────────────────────────────────────────────────────

def get_raster_info(path):
    ds = gdal.Open(path)
    if ds is None:
        raise FileNotFoundError(f"Cannot open raster: {path}")
    gt = ds.GetGeoTransform()
    info = {
        "xres"    : abs(gt[1]),
        "yres"    : abs(gt[5]),
        "cols"    : ds.RasterXSize,
        "rows"    : ds.RasterYSize,
        "xmin"    : gt[0],
        "ymax"    : gt[3],
        "xmax"    : gt[0] + gt[1] * ds.RasterXSize,
        "ymin"    : gt[3] + gt[5] * ds.RasterYSize,
        "nodata"  : ds.GetRasterBand(1).GetNoDataValue(),
        "dtype"   : gdal.GetDataTypeName(ds.GetRasterBand(1).DataType),
    }
    ds = None
    return info


def is_categorical(path):
    """Detect categorical rasters (byte/integer dtype) → use nearest neighbour."""
    ds = gdal.Open(path)
    dtype = ds.GetRasterBand(1).DataType
    ds = None
    return dtype in [gdal.GDT_Byte, gdal.GDT_UInt16, gdal.GDT_Int16,
                     gdal.GDT_UInt32, gdal.GDT_Int32]


def align_raster(input_path, output_path, ref_info, epsg):
    resampling = "near" if is_categorical(input_path) else "bilinear"

    cmd = [
        "gdalwarp",
        "-t_srs", epsg,
        "-tr",    str(ref_info["xres"]), str(ref_info["yres"]),
        "-te",
            str(ref_info["xmin"]),
            str(ref_info["ymin"]),
            str(ref_info["xmax"]),
            str(ref_info["ymax"]),
        "-tap",
        "-r",     resampling,
        "-dstnodata", str(NODATA),
        "-of",    "GTiff",
        "-co",    "COMPRESS=LZW",
        "-co",    "TILED=YES",
        "-co",    "BLOCKXSIZE=256",
        "-co",    "BLOCKYSIZE=256",
        "-co",    "BIGTIFF=IF_SAFER",
        "-overwrite",
        input_path,
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return resampling, result


def resolve_reference():
    """
    If REFERENCE is explicitly set, use it.
    Otherwise scan G:\\Processed and auto-pick the first .tif found.
    """
    if REFERENCE:
        if not os.path.isfile(REFERENCE):
            raise FileNotFoundError(f"Specified reference not found: {REFERENCE}")
        return REFERENCE

    ref_files = [
        f for f in os.listdir(REF_DIR)
        if f.lower().endswith((".tif", ".tiff"))
    ]
    if not ref_files:
        raise FileNotFoundError(f"No TIF files found in reference directory: {REF_DIR}")

    # Sort for reproducibility and pick first
    ref_files.sort()
    return os.path.join(REF_DIR, ref_files[0])


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Resolve reference raster ───────────────────────────────
    ref_path = resolve_reference()
    ref_info = get_raster_info(ref_path)

    print("=" * 55)
    print("GDAL RASTER ALIGNMENT")
    print("=" * 55)
    print(f"Reference raster : {ref_path}")
    print(f"Target resolution: {ref_info['xres']} x {ref_info['yres']} m")
    print(f"Target dimensions: {ref_info['cols']} cols x {ref_info['rows']} rows")
    print(f"Target extent    : {ref_info['xmin']:.4f}, {ref_info['ymin']:.4f}, "
          f"{ref_info['xmax']:.4f}, {ref_info['ymax']:.4f}")
    print(f"Input directory  : {INPUT_DIR}")
    print(f"Output directory : {OUTPUT_DIR}")
    print("=" * 55)

    # ── Collect input rasters ──────────────────────────────────
    tif_files = sorted([
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith((".tif", ".tiff"))
    ])

    if not tif_files:
        print("No TIF files found in input directory.")
        return

    print(f"Found {len(tif_files)} raster(s) to process.\n")

    passed, failed = [], []

    for i, fname in enumerate(tif_files, 1):
        input_path  = os.path.join(INPUT_DIR, fname)
        output_path = os.path.join(OUTPUT_DIR, f"aligned_{fname}")

        resampling, result = align_raster(input_path, output_path, ref_info, EPSG)

        if result.returncode == 0:
            out_info = get_raster_info(output_path)
            status = "OK" if (
                out_info["cols"] == ref_info["cols"] and
                out_info["rows"] == ref_info["rows"]
            ) else "WARNING: dimension mismatch"
            print(f"[{i}/{len(tif_files)}] {fname}")
            print(f"    resampling : {resampling}")
            print(f"    dimensions : {out_info['cols']} cols x {out_info['rows']} rows  [{status}]")
            print(f"    resolution : {out_info['xres']} x {out_info['yres']} m")
            passed.append(fname)
        else:
            print(f"[{i}/{len(tif_files)}] FAILED: {fname}")
            print(f"    {result.stderr.strip()}")
            failed.append(fname)

    # ── Output Summary ────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print(f"SUMMARY: {len(passed)} passed  |  {len(failed)} failed")
    if failed:
        print("Failed files:")
        for f in failed:
            print(f"  - {f}")
    print(f"Aligned rasters saved to: {OUTPUT_DIR}")
    print("=" * 55)


if __name__ == "__main__":
    main()
