$(function () {
    var socket = new io.connect(window.location.hostname + ':5000/socket');
    socket.on('data', function (data) {
        var img = new Image();
        if (data.cover) $(img).attr('src', './static/cover.jpg').attr('class', 'cover');
        else $(img).attr('src', './static/blank.jpg').attr('class', 'cover');
        if (data.artist == '' && data.title == '' && !data.cover) document.title = 'VinyListen';
        else document.title = 'Now playing: ' + data.title + ' - ' + data.artist;
        $(img).on('load', function () {
            var vibrant = new Vibrant(img);
            var swatches = vibrant.swatches();
            if (swatches['Vibrant'] && swatches['DarkVibrant']) $('body').css('background-image', 'linear-gradient(' + swatches['Vibrant'].getHex() + ', ' + swatches['DarkVibrant'].getHex() + ')');
            else $('body').css('background-image', 'linear-gradient(grey, black)');
            if ($('.container>img').length) $('.container>img').replaceWith($(img));
            else $('.container').prepend(img);
        });
        $('.title').text(data.title);
        $('.artist').text(data.artist);
    });
});