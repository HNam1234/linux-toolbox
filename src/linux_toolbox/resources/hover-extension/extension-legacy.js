const { Clutter, GLib, Pango, St } = imports.gi;
const Main = imports.ui.main;

const HOVER_DELAY_MS = 220;
const HIDE_DELAY_MS = 260;
const POINTER_POLL_MS = 90;
const POPUP_GAP = 12;
const POPUP_MARGIN = 8;
const PREVIEW_WIDTH = 260;
const PREVIEW_HEIGHT = 160;

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function hasStyleClass(actor, className) {
    if (!actor || typeof actor.get_style_class_name !== 'function')
        return false;
    const style = actor.get_style_class_name();
    return typeof style === 'string' && style.split(/\s+/).indexOf(className) !== -1;
}

function getActorName(actor) {
    if (!actor)
        return '';
    if (typeof actor.get_name === 'function')
        return actor.get_name() || '';
    return actor.name || '';
}

function actorLooksLikeDock(actor) {
    const name = getActorName(actor);
    return name === 'dash' || name === 'dashtodockContainer' ||
        hasStyleClass(actor, 'dash') ||
        hasStyleClass(actor, 'dash-item') ||
        hasStyleClass(actor, 'dash-item-container') ||
        hasStyleClass(actor, 'app-well-app');
}

function getVisibleAppWindows(app) {
    if (!app || typeof app.get_windows !== 'function')
        return [];
    return app.get_windows().filter(window => {
        if (!window)
            return false;
        if (typeof window.is_skip_taskbar === 'function')
            return !window.is_skip_taskbar();
        return !window.skip_taskbar;
    }).sort((left, right) => {
        const leftTime = typeof left.get_user_time === 'function' ? left.get_user_time() : 0;
        const rightTime = typeof right.get_user_time === 'function' ? right.get_user_time() : 0;
        return rightTime - leftTime;
    });
}

class WindowPreviewPopup {
    constructor() {
        this._sourceActor = null;
        this.actor = new St.BoxLayout({
            style_class: 'dock-preview-popup',
            vertical: true,
            reactive: true,
            can_focus: true,
            track_hover: true,
            visible: false,
        });
        Main.layoutManager.addTopChrome(this.actor);
    }

    get visible() {
        return this.actor.visible;
    }

    containsActor(actor) {
        for (let current = actor; current; current = current.get_parent()) {
            if (current === this.actor)
                return true;
        }
        return false;
    }

    show(app, windows, sourceActor) {
        if (!sourceActor || windows.length === 0)
            return;
        this._sourceActor = sourceActor;
        this._clearChildren();
        this.actor.add_child(new St.Label({
            style_class: 'dock-preview-header',
            text: app.get_name(),
            x_align: Clutter.ActorAlign.START,
        }));
        const itemsContainer = new St.BoxLayout({
            style_class: 'dock-preview-items',
            vertical: true,
            x_expand: true,
        });
        this.actor.add_child(itemsContainer);
        for (const window of windows)
            itemsContainer.add_child(this._createWindowButton(window, app));
        this.actor.show();
        this._positionNearSource();
    }

    hide() {
        this._sourceActor = null;
        this.actor.hide();
    }

    destroy() {
        this._clearChildren();
        Main.layoutManager.removeChrome(this.actor);
        this.actor.destroy();
        this.actor = null;
    }

    _clearChildren() {
        for (const child of this.actor.get_children())
            child.destroy();
    }

    _createWindowButton(metaWindow, app) {
        const button = new St.Button({
            style_class: 'dock-preview-item',
            reactive: true,
            can_focus: true,
            track_hover: true,
            x_expand: true,
        });
        const layout = new St.BoxLayout({ vertical: true, x_expand: true });
        layout.add_child(this._createThumbnail(metaWindow, app));
        layout.add_child(this._createTitleLabel(metaWindow, app));
        button.set_child(layout);
        button.connect('clicked', () => {
            this.hide();
            Main.activateWindow(metaWindow);
        });
        return button;
    }

    _createTitleLabel(metaWindow, app) {
        const titleLabel = new St.Label({
            style_class: 'dock-preview-title',
            text: metaWindow.get_title() || app.get_name(),
            x_align: Clutter.ActorAlign.START,
        });
        titleLabel.set_width(PREVIEW_WIDTH);
        if (titleLabel.clutter_text) {
            titleLabel.clutter_text.single_line_mode = true;
            titleLabel.clutter_text.line_wrap = false;
            titleLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        }
        return titleLabel;
    }

    _createThumbnail(metaWindow, app) {
        const thumbnail = new St.Widget({
            style_class: 'dock-preview-thumb',
            layout_manager: new Clutter.BinLayout(),
            x_expand: true,
        });
        thumbnail.set_size(PREVIEW_WIDTH, PREVIEW_HEIGHT);

        const windowActor = metaWindow.get_compositor_private();
        if (windowActor) {
            try {
                const [sourceWidth, sourceHeight] = windowActor.get_size();
                const width = Math.max(1, sourceWidth);
                const height = Math.max(1, sourceHeight);
                const scale = Math.min(PREVIEW_WIDTH / width, PREVIEW_HEIGHT / height, 1);
                const clone = new Clutter.Clone({
                    source: windowActor,
                    reactive: false,
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                clone.set_size(Math.floor(width * scale), Math.floor(height * scale));
                thumbnail.add_child(clone);
                return thumbnail;
            } catch (error) {
                logError(error, 'Dock Window Preview: failed to clone window actor');
            }
        }

        let icon = null;
        if (typeof app.create_icon_texture === 'function')
            icon = app.create_icon_texture(72);
        if (!icon)
            icon = new St.Icon({ icon_name: 'application-x-executable-symbolic', icon_size: 72 });
        icon.x_align = Clutter.ActorAlign.CENTER;
        icon.y_align = Clutter.ActorAlign.CENTER;
        thumbnail.add_child(icon);
        return thumbnail;
    }

    _positionNearSource() {
        if (!this._sourceActor)
            return;
        const monitor = Main.layoutManager.findMonitorForActor(this._sourceActor) ||
            Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        const [sourceX, sourceY] = this._sourceActor.get_transformed_position();
        const [sourceWidth, sourceHeight] = this._sourceActor.get_transformed_size();
        const [, , popupWidth, popupHeight] = this.actor.get_preferred_size();
        const sourceCenterX = sourceX + sourceWidth / 2;
        const sourceCenterY = sourceY + sourceHeight / 2;
        const side = this._guessDockSide(monitor, sourceCenterX, sourceCenterY);
        let x = sourceX + (sourceWidth - popupWidth) / 2;
        let y = sourceY - popupHeight - POPUP_GAP;
        if (side === St.Side.LEFT) {
            x = sourceX + sourceWidth + POPUP_GAP;
            y = sourceY + (sourceHeight - popupHeight) / 2;
        } else if (side === St.Side.RIGHT) {
            x = sourceX - popupWidth - POPUP_GAP;
            y = sourceY + (sourceHeight - popupHeight) / 2;
        } else if (side === St.Side.TOP) {
            x = sourceX + (sourceWidth - popupWidth) / 2;
            y = sourceY + sourceHeight + POPUP_GAP;
        }
        x = clamp(x, monitor.x + POPUP_MARGIN, monitor.x + monitor.width - popupWidth - POPUP_MARGIN);
        y = clamp(y, monitor.y + POPUP_MARGIN, monitor.y + monitor.height - popupHeight - POPUP_MARGIN);
        this.actor.set_position(Math.round(x), Math.round(y));
    }

    _guessDockSide(monitor, centerX, centerY) {
        const distances = [
            [St.Side.LEFT, Math.abs(centerX - monitor.x)],
            [St.Side.RIGHT, Math.abs(centerX - (monitor.x + monitor.width))],
            [St.Side.TOP, Math.abs(centerY - monitor.y)],
            [St.Side.BOTTOM, Math.abs(centerY - (monitor.y + monitor.height))],
        ];
        distances.sort((left, right) => left[1] - right[1]);
        return distances[0][0];
    }
}

class DockHoverTracker {
    constructor() {
        this._popup = new WindowPreviewPopup();
        this._hoveredIcon = null;
        this._hoveredIconActor = null;
        this._pollId = 0;
        this._showTimeoutId = 0;
        this._hideTimeoutId = 0;
    }

    enable() {
        this._pollId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, POINTER_POLL_MS, () => {
            this._pollPointer();
            return GLib.SOURCE_CONTINUE;
        });
    }

    destroy() {
        this._cancelShow();
        this._cancelHide();
        if (this._pollId) {
            GLib.source_remove(this._pollId);
            this._pollId = 0;
        }
        this._popup.destroy();
        this._popup = null;
    }

    _pollPointer() {
        const actor = this._getPointerActor();
        const hoveredIcon = this._findDockIcon(actor);
        const pointerInPopup = this._popup.containsActor(actor);
        if (hoveredIcon) {
            const iconChanged = hoveredIcon.icon !== this._hoveredIcon ||
                hoveredIcon.actor !== this._hoveredIconActor;
            this._hoveredIcon = hoveredIcon.icon;
            this._hoveredIconActor = hoveredIcon.actor;
            this._cancelHide();
            if (iconChanged)
                this._scheduleShow(hoveredIcon.icon, hoveredIcon.actor);
            return;
        }
        this._hoveredIcon = null;
        this._hoveredIconActor = null;
        this._cancelShow();
        if (pointerInPopup)
            this._cancelHide();
        else
            this._scheduleHide();
    }

    _getPointerActor() {
        const [x, y] = global.get_pointer();
        return global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, x, y);
    }

    _findDockIcon(actor) {
        for (let current = actor; current; current = current.get_parent()) {
            const delegate = this._getDockIconDelegate(current);
            if (!delegate || !delegate.app)
                continue;
            if (!this._isInsideDock(current, delegate))
                continue;
            return { icon: delegate, actor: this._getIconActor(delegate, current) };
        }
        return null;
    }

    _getDockIconDelegate(actor) {
        const candidates = [actor, actor ? actor._delegate : null];
        if (actor && actor.child) {
            candidates.push(actor.child);
            candidates.push(actor.child._delegate);
        }
        for (const candidate of candidates) {
            if (this._isDockAppIcon(candidate))
                return candidate;
        }
        return null;
    }

    _isDockAppIcon(delegate) {
        return !!delegate && !!delegate.app &&
            (typeof delegate.getInterestingWindows === 'function' ||
                typeof delegate.getWindows === 'function' ||
                typeof delegate.app.get_windows === 'function');
    }

    _isInsideDock(actor, delegate) {
        if (delegate && delegate.monitorIndex !== undefined)
            return true;
        for (let current = actor; current; current = current.get_parent()) {
            if (actorLooksLikeDock(current))
                return true;
        }
        return false;
    }

    _getIconActor(icon, fallbackActor) {
        if (icon instanceof Clutter.Actor)
            return icon;
        if (icon.actor instanceof Clutter.Actor)
            return icon.actor;
        if (icon._delegate instanceof Clutter.Actor)
            return icon._delegate;
        return fallbackActor;
    }

    _scheduleShow(icon, actor) {
        this._cancelShow();
        this._cancelHide();
        this._showTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HOVER_DELAY_MS, () => {
            this._showTimeoutId = 0;
            if (this._hoveredIcon !== icon || this._hoveredIconActor !== actor)
                return GLib.SOURCE_REMOVE;
            const windows = this._getAppWindows(icon);
            if (windows.length === 0) {
                this._popup.hide();
                return GLib.SOURCE_REMOVE;
            }
            this._popup.show(icon.app, windows, actor);
            return GLib.SOURCE_REMOVE;
        });
    }

    _scheduleHide() {
        if (this._hideTimeoutId || !this._popup.visible)
            return;
        this._hideTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, HIDE_DELAY_MS, () => {
            this._hideTimeoutId = 0;
            this._popup.hide();
            return GLib.SOURCE_REMOVE;
        });
    }

    _cancelShow() {
        if (this._showTimeoutId) {
            GLib.source_remove(this._showTimeoutId);
            this._showTimeoutId = 0;
        }
    }

    _cancelHide() {
        if (this._hideTimeoutId) {
            GLib.source_remove(this._hideTimeoutId);
            this._hideTimeoutId = 0;
        }
    }

    _getAppWindows(icon) {
        let windows = [];
        if (typeof icon.getInterestingWindows === 'function')
            windows = icon.getInterestingWindows();
        if (windows.length === 0 && typeof icon.getWindows === 'function')
            windows = icon.getWindows();
        if (windows.length === 0 && icon.app && typeof icon.app.get_windows === 'function')
            windows = icon.app.get_windows();
        return getVisibleAppWindows({ get_windows: () => windows });
    }
}

let tracker = null;

function init() {
}

function enable() {
    if (tracker)
        return;
    tracker = new DockHoverTracker();
    tracker.enable();
}

function disable() {
    if (!tracker)
        return;
    tracker.destroy();
    tracker = null;
}
