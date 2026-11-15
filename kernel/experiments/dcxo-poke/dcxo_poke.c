// SPDX-License-Identifier: GPL-2.0
/*
 * Experiment: switch MT6359 DCXO clock buffers to software mode, on.
 * DCXO_CW00 (0x788): EXTBUFn_MODE at bits [3n-3+1:3n-3]..., per the
 * vendor clkbuf driver: EXTBUF2 (XO_WCN) mode [4:3] en_m 5,
 * EXTBUF3 (XO_NFC) mode [7:6] en_m 8.
 */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/device.h>

static int bufs = 0x2;	/* bit0: XO_WCN, bit1: XO_NFC */
module_param(bufs, int, 0444);
#define DCXO_CW00 0x788

static int __init dcxo_poke_init(void)
{
	struct device *dev;
	struct regmap *map;
	unsigned int before, after;
	unsigned int mask = 0, val = 0;
	int ret;

	dev = bus_find_device_by_name(&platform_bus_type, NULL, "1000d000.pwrap");
	if (!dev)
		return -ENODEV;
	map = dev_get_regmap(dev, NULL);
	put_device(dev);
	if (!map)
		return -ENODEV;
	if (bufs & 1) { mask |= (3 << 3) | BIT(5); val |= BIT(5); }
	if (bufs & 2) { mask |= (3 << 6) | BIT(8); val |= BIT(8); }
	regmap_read(map, DCXO_CW00, &before);
	ret = regmap_update_bits(map, DCXO_CW00, mask, val);
	regmap_read(map, DCXO_CW00, &after);
	pr_err("dcxo-poke: CW00 %04x -> %04x (bufs=%d, ret=%d)\n", before, after, bufs, ret);
	return 0;
}

static void __exit dcxo_poke_exit(void) { }

module_init(dcxo_poke_init);
module_exit(dcxo_poke_exit);
MODULE_LICENSE("GPL");
