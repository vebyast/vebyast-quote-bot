var QUOTEDB_DOCUMENTS;
var QUOTEDB_MAP;
var idx;
$.getJSON('quotes.json', reindex);

function reindex(json) {
	QUOTEDB_DOCUMENTS = json;

	QUOTEDB_MAP = {};
	QUOTEDB_DOCUMENTS.forEach(function (doc) {
		QUOTEDB_MAP[doc['id']] = doc;
		doc['text'] = doc['lines'].join("<br />");
		doc['uploaded'] = Date.parse(doc['uploaded']);
	});

	idx = lunr(function () {
		this.ref('id');
		this.field('text');
		this.field('users');

		QUOTEDB_DOCUMENTS.forEach(function (doc) {
			this.add(doc);
		}, this);
	});
}



var search_results_vue;
$(document).ready(function() {
	search_results_vue = new Vue({
		el: '#search_results',
		data: {
			search_results: [],
		}
	});

	$('#search_query_box').keypress(function(e) {
        if (e.keyCode == 13) {
			$('#search_query_submit_button').click();
			return false;
		};
	});
});

function search_quote_db() {
	query = $('#search_query_box').val();
	results = idx.search(query);
	result_documents = results.map(function(sr) {
		doc = QUOTEDB_MAP[sr.ref]
		return {
			"uploaded": (new Date(doc["uploaded"])).toLocaleDateString(),
			"lines": doc["lines"],
		}
	});
	search_results_vue.search_results = result_documents;
};
