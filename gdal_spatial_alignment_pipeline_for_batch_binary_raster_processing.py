# ────Import dependencies──────────────────────────────────────────────────────────
import subprocess
import os
from osgeo import gdal

# ──Directories & Configuration─────────────────────────────────────────────
INPUT_DIR   = r"G:\Raster_Source"
OUTPUT_DIR  = r"G:\Raster_Source\Aligned_Raster"  # Auto_created OUTPUT folder
REF_DIR     = r"G:\Ref_Source\Reference_Raster.tif"
REFERENCE   = None   # Set to r"G:\Ref_Source\Reference_Raster.tif" or leave None to auto-pick
NODATA      = -9999  # Use only for continuous rasters
EPSG        = "EPSG:32646"  # Change to CRS
# ──────────────────────────────────────────────────────────────


def get_raster_info(path):
    ds = gdal.Open(path)
    if ds is None:
        raise FileNotFoundError(f"Cannot open raster: {path}")
    gt = ds.GetGeoTransform()
    info = {
        "xres"   : abs(gt[1]),
        "yres"   : abs(gt[5]),
        "cols"   : ds.RasterXSize,
        "rows"   : ds.RasterYSize,
        "xmin"   : gt[0],
        "ymax"   : gt[3],
        "xmax"   : gt[0] + gt[1] * ds.RasterXSize,
        "ymin"   : gt[3] + gt[5] * ds.RasterYSize,
        "nodata" : ds.GetRasterBand(1).GetNoDataValue(),
        "dtype"  : gdal.GetDataTypeName(ds.GetRasterBand(1).DataType),
    }
    ds = None
    return info


def is_categorical(path):
    """Integer/byte dtype → categorical raster."""
    ds = gdal.Open(path)
    dtype = ds.GetRasterBand(1).DataType
    ds = None
    return dtype in [gdal.GDT_Byte, gdal.GDT_UInt16, gdal.GDT_Int16,
                     gdal.GDT_UInt32, gdal.GDT_Int32]


def is_binary(path):
    """
    Detect binary rasters (only values 0 and 1) using GDAL histogram.
    No NumPy dependency — avoids gdal_array conflicts entirely.
    """
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    nodata_val = band.GetNoDataValue()

    hist = band.GetHistogram(min=-0.5, max=255.5, buckets=256,
                             include_out_of_range=0, approx_ok=1)
    ds = None

    if hist is None:
        return False

    for i, count in enumerate(hist):
        if count > 0 and i not in (0, 1):
            if nodata_val is not None and abs(i - nodata_val) < 0.5:
                continue
            return False
    return True


def verify_binary_output(path):
    """
    Confirm aligned binary raster contains only 0, 1, and nodata (255).
    Uses GDAL histogram — no NumPy dependency.
    Returns (passed, unique_values_set).
    """
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)

    hist = band.GetHistogram(min=-0.5, max=255.5, buckets=256,
                             include_out_of_range=0, approx_ok=1)
    ds = None

    if hist is None:
        return False, set()

    present_vals = {i for i, count in enumerate(hist)
                    if count > 0 and i != 255}
    passed = present_vals.issubset({0, 1})
    return passed, present_vals


def align_raster(input_path, output_path, ref_info, epsg):
    """
    Align a single raster to the reference grid.
    - Binary rasters  → mode resampling, dstnodata=255, no srcnodata declared
    - Categorical     → nearest neighbour, dstnodata=-9999
    - Continuous      → bilinear, dstnodata=-9999
    """
    categorical = is_categorical(input_path)
    binary      = categorical and is_binary(input_path)

    if binary:
        resampling   = "mode"
        src_nodata   = []
        dst_nodata   = ["255"]
        output_dtype = ["-ot", "Byte"]
    elif categorical:
        resampling   = "near"
        src_nodata   = ["-srcnodata", str(NODATA)]
        dst_nodata   = [str(NODATA)]
        output_dtype = []
    else:
        resampling   = "bilinear"
        src_nodata   = ["-srcnodata", str(NODATA)]
        dst_nodata   = [str(NODATA)]
        output_dtype = []

    cmd = (
        ["gdalwarp"]
        + output_dtype
        + ["-t_srs", epsg]
        + ["-tr", str(ref_info["xres"]), str(ref_info["yres"])]
        + ["-te",
           str(ref_info["xmin"]),
           str(ref_info["ymin"]),
           str(ref_info["xmax"]),
           str(ref_info["ymax"])]
        + ["-tap"]
        + ["-r", resampling]
        + src_nodata
        + ["-dstnodata"] + dst_nodata
        + ["-of", "GTiff"]
        + ["-co", "COMPRESS=LZW"]
        + ["-co", "TILED=YES"]
        + ["-co", "BLOCKXSIZE=256"]
        + ["-co", "BLOCKYSIZE=256"]
        + ["-co", "BIGTIFF=IF_SAFER"]
        + ["-overwrite"]
        + [input_path, output_path]
    )

    result = subprocess.run(cmd, capture_output=True, text=True)
    return resampling, binary, result


def resolve_reference():
    """
    Use explicitly set REFERENCE path, or auto-pick the
    first .tif found in REF_DIR alphabetically.
    """
    if REFERENCE:
        if not os.path.isfile(REFERENCE):
            raise FileNotFoundError(f"Specified reference not found: {REFERENCE}")
        return REFERENCE

    ref_files = sorted([
        f for f in os.listdir(REF_DIR)
        if f.lower().endswith((".tif", ".tiff"))
    ])
    if not ref_files:
        raise FileNotFoundError(
            f"No TIF files found in reference directory: {REF_DIR}"
        )
    return os.path.join(REF_DIR, ref_files[0])


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Resolve reference raster ───────────────────────────────
    ref_path = resolve_reference()
    ref_info = get_raster_info(ref_path)

    print("=" * 60)
    print("GDAL BATCH RASTER ALIGNMENT PIPELINE")
    print("=" * 60)
    print(f"Reference raster : {ref_path}")
    print(f"Target resolution: {ref_info['xres']} x {ref_info['yres']} m")
    print(f"Target dimensions: {ref_info['cols']} cols x {ref_info['rows']} rows")
    print(f"Target extent    : {ref_info['xmin']:.4f}, {ref_info['ymin']:.4f}, "
          f"{ref_info['xmax']:.4f}, {ref_info['ymax']:.4f}")
    print(f"Input directory  : {INPUT_DIR}")
    print(f"Output directory : {OUTPUT_DIR}")
    print("=" * 60)

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

        resampling, binary, result = align_raster(
            input_path, output_path, ref_info, EPSG
        )

        if result.returncode == 0:
            out_info = get_raster_info(output_path)
            dim_ok   = (out_info["cols"] == ref_info["cols"] and
                        out_info["rows"] == ref_info["rows"])
            dim_flag = "OK" if dim_ok else "WARNING: dimension mismatch"

            raster_type = (
                "BINARY (0/1)" if binary
                else "categorical" if is_categorical(input_path)
                else "continuous"
            )

            print(f"[{i}/{len(tif_files)}] {fname}")
            print(f"    type       : {raster_type}")
            print(f"    resampling : {resampling}")
            print(f"    dimensions : {out_info['cols']} cols x "
                  f"{out_info['rows']} rows  [{dim_flag}]")
            print(f"    resolution : {out_info['xres']} x {out_info['yres']} m")

            # Binary integrity check
            if binary:
                val_ok, unique_vals = verify_binary_output(output_path)
                integrity = "PASSED" if val_ok else "FAILED — unexpected values detected"
                print(f"    binary check: unique values = {unique_vals}  [{integrity}]")

            passed.append(fname)

        else:
            print(f"[{i}/{len(tif_files)}] FAILED: {fname}")
            print(f"    {result.stderr.strip()}")
            failed.append(fname)

    # ── Output Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"SUMMARY: {len(passed)} passed  |  {len(failed)} failed")
    if failed:
        print("Failed files:")
        for f in failed:
            print(f"  - {f}")
    print(f"Aligned rasters saved to: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
