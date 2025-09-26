const DURATION_UNITS = [
    { name: "year", value: 31536000 }, // 365 * 24 * 60 * 60
    { name: "month", value: 2592000 }, // 30 * 24 * 60 * 60
    { name: "week", value: 604800 }, // 7 * 24 * 60 * 60
    { name: "day", value: 86400 }, // 24 * 60 * 60
    { name: "hour", value: 3600 }, // 60 * 60
    { name: "minute", value: 60 },
    { name: "second", value: 1 },
];

const SIZE_UNITS = [
    { name: "B", value: 1 },
    { name: "KB", value: 1024 },
    { name: "MB", value: 1048576 }, // 1024 * 1024
    { name: "GB", value: 1073741824 }, // 1024 * 1024 * 1024
    { name: "TB", value: 1099511627776 }, // 1024 * 1024 * 1024 * 1024
];

export const humanDuration = (seconds: number): string => {
    const abs = Math.abs(Math.floor(seconds));
    if (abs === 0) return "0 seconds";
    const unit = DURATION_UNITS.find((u) => abs >= u.value)!;
    const count = Math.floor(abs / unit.value);
    return `${count} ${unit.name}${count === 1 ? "" : "s"}`;
};

export const humanSize = (size: number): string => {
    const abs = Math.abs(size);
    if (abs === 0) return "0 B";
    const unit = SIZE_UNITS.find((u) => abs < u.value * 1024)!;
    const count = size / unit.value;
    return `${count.toFixed(2)} ${unit.name}`;
};

export const humanTimestamp = (timestamp: string | number | Date): string => {
    const date = new Date(timestamp);
    return date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
};
