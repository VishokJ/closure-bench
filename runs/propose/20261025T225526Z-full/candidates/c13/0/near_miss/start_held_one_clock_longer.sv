`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b1;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd5;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int   n_valid = 0;
  int   n_err = 0;
  logic [7:0] got;

  always @(negedge clk) begin
    if (!rst) begin
      if (m_axis_tvalid) begin got = m_axis_tdata; n_valid++; end
      if (frame_error || overrun_error) n_err++;
    end
  end

  int cnt;
  initial begin
    repeat (3) @(negedge clk);
    rst = 1'b0;
    repeat (5) @(negedge clk);
    if (busy) $fatal(1, "busy high while idle");

    // rxd low for 20 clocks: one clock longer than the gold, so the
    // mid-start-bit check sees rxd low and the start is accepted.
    rxd = 1'b0;
    cnt = 0;
    for (int i = 0; i < 500; i++) begin
      @(negedge clk);
      if (i == 19) rxd = 1'b1;
      if (busy) cnt++;
    end
    if (cnt <= 20) $fatal(1, "start was rejected (busy for %0d clocks)", cnt);
    if (busy) $fatal(1, "busy still high after frame");
    if (n_valid != 1) $fatal(1, "expected 1 word, got %0d", n_valid);
    if (got !== 8'hFF) $fatal(1, "got 0x%02h expected 0xFF", got);
    if (n_err != 0) $fatal(1, "unexpected error strobe");
    $display("PASS near miss");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
